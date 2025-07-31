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


class SignalHandler:
    """Singleton class to handle signals for graceful shutdown."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SignalHandler, cls).__new__(cls)
            cls._instance.agent = None
            cls._instance.loop = None
            cls._instance.shutdown_future = None
            cls._instance.shutting_down = False
        return cls._instance
        
    def register_agent(self, agent):
        self.agent = agent
        
    def register_loop(self, loop: asyncio.AbstractEventLoop, shutdown_future: asyncio.Future):
        self.loop = loop
        self.shutdown_future = shutdown_future
        
    def is_shutting_down(self) -> bool:
        return self.shutting_down

    async def shutdown(self, signum=None):
        if self.shutting_down:
            return
            
        self.shutting_down = True
        
        if signum:
            logger.info(f"Received signal {signum.name}, initiating graceful shutdown...")
        else:
            logger.info("Shutdown requested, initiating graceful shutdown...")

        if self.agent:
            logger.info("Cleaning up agent...")
            await self.agent.cleanup()
            logger.info("Agent cleanup complete.")
        
        # Signal the main loop to exit
        if self.shutdown_future and not self.shutdown_future.done():
            self.shutdown_future.set_result(True)

        # The original implementation's loop stopping logic can be removed
        # as the future will now handle this.
        
        logger.info("Graceful shutdown complete.")


# Global signal handler instance
_signal_handler_instance = SignalHandler()

def get_signal_handler() -> SignalHandler:
    """Return the singleton instance of the signal handler."""
    return _signal_handler_instance

def setup_signal_handlers():
    """Set up OS signal handlers to trigger graceful shutdown."""
    handler = get_signal_handler()
    loop = handler.loop
    
    if loop:
        for signame in ('SIGINT', 'SIGTERM'):
            sig = getattr(signal, signame)
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(handler.shutdown(s))
            )
        logger.info(f"✅ Signal handlers registered (SIGINT, SIGTERM)")
    else:
        logger.warning("⚠️  No event loop registered, could not set up signal handlers.")