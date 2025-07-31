"""
Robust signal handling for MaestroCat with graceful shutdown coordination.

This module provides comprehensive signal handling for SIGINT (Ctrl+C) and SIGTERM
(container shutdown) with proper async cleanup coordination and resource management.
"""

import asyncio
import logging
import signal
import sys
import threading
import time
from typing import Optional, List, Callable, Any
import os

logger = logging.getLogger(__name__)


class MaestroCatSignalHandler:
    """
    Centralized signal handler for MaestroCat applications.
    
    Provides robust handling of SIGINT and SIGTERM signals with:
    - Graceful async cleanup coordination
    - Resource cleanup across all components
    - Timeout handling for stuck operations
    - Fallback mechanisms for edge cases
    - Thread-safe operation
    """
    
    def __init__(self):
        self._shutdown_event = threading.Event()
        self._cleanup_lock = threading.Lock()
        self._cleanup_complete = False
        self._cleanup_callbacks: List[Callable[[], Any]] = []
        self._async_cleanup_callbacks: List[Callable[[], Any]] = []
        self._agent = None
        self._loop = None
        self._original_handlers = {}
        
    def register_agent(self, agent):
        """Register the agent instance for cleanup"""
        self._agent = agent
        
    def register_loop(self, loop: asyncio.AbstractEventLoop):
        """Register the asyncio event loop"""
        self._loop = loop
        
    def add_cleanup_callback(self, callback: Callable[[], Any], async_callback: bool = False):
        """
        Add a cleanup callback to be executed during shutdown.
        
        Args:
            callback: Function to call during cleanup
            async_callback: True if callback is async, False for sync
        """
        if async_callback:
            self._async_cleanup_callbacks.append(callback)
        else:
            self._cleanup_callbacks.append(callback)
            
    def is_shutting_down(self) -> bool:
        """Check if shutdown is in progress"""
        return self._shutdown_event.is_set()
        
    def _signal_handler(self, signum: int, frame):
        """Handle OS signals for graceful shutdown"""
        signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        
        if self._shutdown_event.is_set():
            logger.warning(f"⚠️  {signal_name} received but shutdown already in progress, forcing exit...")
            os._exit(1)
            
        logger.info(f"🛑 Received {signal_name}, initiating graceful shutdown...")
        self._shutdown_event.set()
        
        # Schedule async cleanup on the event loop
        if self._loop and not self._loop.is_closed():
            try:
                # Use call_soon_threadsafe for thread safety
                self._loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._async_cleanup())
                )
                
                # Start a watchdog thread that will force exit after timeout
                def force_exit_watchdog():
                    time.sleep(30)  # 30 second total timeout
                    if not self._cleanup_complete:
                        logger.error("⏰ Cleanup timeout exceeded, forcing exit...")
                        os._exit(1)
                
                watchdog = threading.Thread(target=force_exit_watchdog, daemon=True)
                watchdog.start()
                
            except Exception as e:
                logger.error(f"❌ Error scheduling async cleanup: {e}")
                threading.Thread(target=self._sync_cleanup, daemon=True).start()
        else:
            # Fallback to thread-based cleanup
            threading.Thread(target=self._sync_cleanup, daemon=True).start()
            
    async def _async_cleanup(self):
        """Async cleanup with proper coordination and timeout handling"""
        if self._cleanup_complete:
            return
            
        with self._cleanup_lock:
            if self._cleanup_complete:
                return
                
            start_time = time.time()
            logger.info("🧹 Starting async cleanup sequence...")
            
            try:
                # Execute async cleanup callbacks
                await self._execute_async_cleanup_callbacks()
                
                # Execute sync cleanup callbacks
                await self._execute_sync_cleanup_callbacks()
                
                # Cleanup agent if available
                if self._agent:
                    await self._cleanup_agent()
                
                # Cancel all running tasks
                await self._cancel_all_tasks()
                
                self._cleanup_complete = True
                elapsed = time.time() - start_time
                logger.info(f"✅ Cleanup sequence complete ({elapsed:.2f}s)")
                
            except Exception as e:
                logger.error(f"❌ Error during async cleanup: {e}")
            finally:
                # Stop the event loop to ensure all tasks are cancelled
                if self._loop and self._loop.is_running():
                    self._loop.stop()
                
                # Ensure we exit even if cleanup had errors
                os._exit(0)
                
    async def _execute_async_cleanup_callbacks(self):
        """Execute all async cleanup callbacks with timeout"""
        if not self._async_cleanup_callbacks:
            return
            
        logger.info(f"🔄 Executing {len(self._async_cleanup_callbacks)} async cleanup callbacks...")
        
        # Create tasks for all async callbacks
        tasks = []
        for callback in self._async_cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    task = asyncio.create_task(callback())
                    tasks.append(task)
                else:
                    logger.warning(f"⚠️  Async callback {callback} is not a coroutine function")
            except Exception as e:
                logger.error(f"❌ Error creating async cleanup task: {e}")
        
        if tasks:
            try:
                # Wait for all tasks with timeout
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("⏰ Async cleanup callbacks timed out")
                
    async def _execute_sync_cleanup_callbacks(self):
        """Execute all sync cleanup callbacks in executor"""
        if not self._cleanup_callbacks:
            return
            
        logger.info(f"🔄 Executing {len(self._cleanup_callbacks)} sync cleanup callbacks...")
        
        # Run sync callbacks in thread pool
        loop = asyncio.get_event_loop()
        for callback in self._cleanup_callbacks:
            try:
                await loop.run_in_executor(None, callback)
            except Exception as e:
                logger.error(f"❌ Error executing sync cleanup callback: {e}")
                
    async def _cleanup_agent(self):
        """Clean up the registered agent with timeout"""
        if not self._agent:
            return
            
        logger.info("🧹 Cleaning up agent resources...")
        try:
            if hasattr(self._agent, 'cleanup'):
                await asyncio.wait_for(
                    self._agent.cleanup(),
                    timeout=15.0
                )
            else:
                logger.warning("⚠️  Agent has no cleanup method")
        except asyncio.TimeoutError:
            logger.error("⏰ Agent cleanup timed out")
        except Exception as e:
            logger.error(f"❌ Error during agent cleanup: {e}")
            
    async def _cancel_all_tasks(self):
        """Cancel all running asyncio tasks except current"""
        try:
            current_task = asyncio.current_task()
            tasks = [t for t in asyncio.all_tasks() if t is not current_task]
            
            if tasks:
                logger.info(f"🔄 Cancelling {len(tasks)} running tasks...")
                for task in tasks:
                    task.cancel()
                
                # Wait for tasks to complete with timeout
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("⏰ Task cancellation timed out")
                    
        except Exception as e:
            logger.error(f"❌ Error cancelling tasks: {e}")
            
    def _sync_cleanup(self):
        """Synchronous cleanup fallback for edge cases"""
        if self._cleanup_complete:
            return
            
        with self._cleanup_lock:
            if self._cleanup_complete:
                return
                
            logger.info("🧹 Starting sync cleanup sequence...")
            
            try:
                # Execute sync cleanup callbacks
                for callback in self._cleanup_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        logger.error(f"❌ Error in sync cleanup callback: {e}")
                
                # Try to run agent cleanup if possible
                if self._agent and hasattr(self._agent, 'cleanup'):
                    try:
                        import asyncio
                        if asyncio.get_event_loop().is_running():
                            asyncio.create_task(self._agent.cleanup())
                        else:
                            asyncio.run(self._agent.cleanup())
                    except Exception as e:
                        logger.error(f"❌ Error in sync agent cleanup: {e}")
                        
                self._cleanup_complete = True
                logger.info("✅ Sync cleanup complete")
                
            except Exception as e:
                logger.error(f"❌ Error during sync cleanup: {e}")
            finally:
                os._exit(0)
                
    def register_signals(self):
        """Register signal handlers for SIGINT and SIGTERM"""
        try:
            # Store original handlers
            self._original_handlers[signal.SIGINT] = signal.getsignal(signal.SIGINT)
            self._original_handlers[signal.SIGTERM] = signal.getsignal(signal.SIGTERM)
            
            # Register new handlers
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            logger.info("✅ Signal handlers registered (SIGINT, SIGTERM)")
            
        except ValueError as e:
            # This happens in threads or when signals can't be registered
            logger.warning(f"⚠️  Could not register signal handlers: {e}")
            
    def unregister_signals(self):
        """Restore original signal handlers"""
        try:
            for signum, handler in self._original_handlers.items():
                signal.signal(signum, handler)
            logger.info("✅ Original signal handlers restored")
        except Exception as e:
            logger.error(f"❌ Error restoring signal handlers: {e}")


# Global signal handler instance
_signal_handler_instance = None


def get_signal_handler() -> MaestroCatSignalHandler:
    """Get the global signal handler instance"""
    global _signal_handler_instance
    if _signal_handler_instance is None:
        _signal_handler_instance = MaestroCatSignalHandler()
    return _signal_handler_instance


def setup_signal_handlers(agent=None, loop=None):
    """
    Convenience function to set up signal handlers.
    
    Args:
        agent: The MaestroCatAgent instance to register
        loop: The asyncio event loop to use
    """
    handler = get_signal_handler()
    
    if agent:
        handler.register_agent(agent)
    if loop:
        handler.register_loop(loop)
        
    handler.register_signals()
    return handler