# Memory Leak Prevention System
"""
Memory monitoring and leak prevention for long-running MaestroCat services.
Provides automatic garbage collection, memory threshold monitoring, and leak detection.
"""

import asyncio
import gc
import time
import logging
import psutil
import weakref
from typing import Dict, Any, Optional, Callable, List, Set
from dataclasses import dataclass
from enum import Enum
import tracemalloc
import os

logger = logging.getLogger(__name__)


class MemoryThreshold(Enum):
    """Memory threshold levels"""
    LOW = "low"        # Normal operation
    MEDIUM = "medium"  # Start monitoring closely
    HIGH = "high"      # Take corrective action
    CRITICAL = "critical"  # Emergency cleanup


@dataclass
class MemoryStats:
    """Memory usage statistics"""
    timestamp: float
    process_memory_mb: float
    system_memory_percent: float
    gc_collections: Dict[int, int]
    tracemalloc_current_mb: Optional[float] = None
    tracemalloc_peak_mb: Optional[float] = None
    threshold_level: MemoryThreshold = MemoryThreshold.LOW


class MemoryGuard:
    """
    Memory monitoring and leak prevention system.
    
    Features:
    - Real-time memory monitoring
    - Configurable memory thresholds
    - Automatic garbage collection
    - Memory leak detection using tracemalloc
    - Buffer size management
    - Weak reference tracking
    """
    
    def __init__(
        self,
        service_name: str,
        event_emitter = None,
        enable_tracemalloc: bool = True,
        
        # Memory thresholds in MB
        medium_threshold_mb: int = 512,
        high_threshold_mb: int = 1024,
        critical_threshold_mb: int = 2048,
        
        # Monitoring settings
        check_interval: float = 30.0,
        gc_threshold_multiplier: float = 1.5,
        
        # Buffer management
        max_buffer_sizes: Optional[Dict[str, int]] = None
    ):
        self.service_name = service_name
        self._event_emitter = event_emitter
        self.enable_tracemalloc = enable_tracemalloc
        
        # Thresholds
        self.medium_threshold_mb = medium_threshold_mb
        self.high_threshold_mb = high_threshold_mb
        self.critical_threshold_mb = critical_threshold_mb
        
        # Settings
        self.check_interval = check_interval
        self.gc_threshold_multiplier = gc_threshold_multiplier
        
        # Buffer management
        self.max_buffer_sizes = max_buffer_sizes or {}
        self._managed_buffers: Dict[str, List] = {}
        
        # Monitoring state
        self._monitoring_task: Optional[asyncio.Task] = None
        self._memory_history: List[MemoryStats] = []
        self._max_history = 100
        
        # Leak detection
        self._baseline_objects: Optional[Dict] = None
        self._leak_detection_enabled = False
        self._tracked_objects: Set[weakref.ReferenceType] = set()
        
        # Process reference
        self._process = psutil.Process(os.getpid())
        
        # GC tuning
        self._original_gc_thresholds = gc.get_threshold()
        
    async def start(self):
        """Start memory monitoring"""
        logger.info(f"Starting memory guard for {self.service_name}")
        
        # Enable tracemalloc if requested
        if self.enable_tracemalloc and not tracemalloc.is_tracing():
            tracemalloc.start(25)  # Keep 25 frames in tracebacks
            logger.info("Enabled tracemalloc for memory leak detection")
            
        # Tune garbage collection for better performance
        self._tune_garbage_collection()
        
        # Start monitoring loop
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # Take baseline for leak detection
        await self._take_baseline()
        
        await self._emit_event("memory_guard_started", {
            "medium_threshold_mb": self.medium_threshold_mb,
            "high_threshold_mb": self.high_threshold_mb,
            "critical_threshold_mb": self.critical_threshold_mb
        })
        
    async def stop(self):
        """Stop memory monitoring"""
        logger.info(f"Stopping memory guard for {self.service_name}")
        
        # Stop monitoring
        if self._monitoring_task:
            self._monitoring_task.cancel()
            
        # Restore original GC settings
        gc.set_threshold(*self._original_gc_thresholds)
        
        # Stop tracemalloc
        if tracemalloc.is_tracing():
            tracemalloc.stop()
            
        await self._emit_event("memory_guard_stopped", {})
        
    def _tune_garbage_collection(self):
        """Tune garbage collection for long-running services"""
        # Get current thresholds
        threshold0, threshold1, threshold2 = gc.get_threshold()
        
        # Increase thresholds to reduce GC frequency but increase efficiency
        new_threshold0 = int(threshold0 * self.gc_threshold_multiplier)
        new_threshold1 = int(threshold1 * self.gc_threshold_multiplier)
        new_threshold2 = int(threshold2 * self.gc_threshold_multiplier)
        
        gc.set_threshold(new_threshold0, new_threshold1, new_threshold2)
        
        logger.info(f"Tuned GC thresholds: {self._original_gc_thresholds} -> {gc.get_threshold()}")
        
    async def _monitoring_loop(self):
        """Main memory monitoring loop"""
        while True:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_memory()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in memory monitoring: {e}")
                
    async def _check_memory(self):
        """Check current memory usage and take action if needed"""
        # Get memory statistics
        stats = self._get_memory_stats()
        
        # Store in history
        self._memory_history.append(stats)
        if len(self._memory_history) > self._max_history:
            self._memory_history.pop(0)
            
        # Determine threshold level
        memory_mb = stats.process_memory_mb
        
        if memory_mb >= self.critical_threshold_mb:
            stats.threshold_level = MemoryThreshold.CRITICAL
            await self._handle_critical_memory(stats)
        elif memory_mb >= self.high_threshold_mb:
            stats.threshold_level = MemoryThreshold.HIGH
            await self._handle_high_memory(stats)
        elif memory_mb >= self.medium_threshold_mb:
            stats.threshold_level = MemoryThreshold.MEDIUM
            await self._handle_medium_memory(stats)
        else:
            stats.threshold_level = MemoryThreshold.LOW
            
        # Emit monitoring event
        await self._emit_event("memory_check", {
            "memory_mb": memory_mb,
            "threshold_level": stats.threshold_level.value,
            "system_memory_percent": stats.system_memory_percent
        })
        
        # Check for memory leaks periodically
        if len(self._memory_history) % 10 == 0:  # Every 10 checks
            await self._check_for_leaks()
            
    def _get_memory_stats(self) -> MemoryStats:
        """Get current memory statistics"""
        # Process memory
        memory_info = self._process.memory_info()
        process_memory_mb = memory_info.rss / (1024 * 1024)
        
        # System memory
        system_memory = psutil.virtual_memory()
        system_memory_percent = system_memory.percent
        
        # Garbage collection stats
        gc_stats = {i: gc.get_count()[i] for i in range(3)}
        
        # Tracemalloc stats
        tracemalloc_current_mb = None
        tracemalloc_peak_mb = None
        
        if tracemalloc.is_tracing():
            current_size, peak_size = tracemalloc.get_traced_memory()
            tracemalloc_current_mb = current_size / (1024 * 1024)
            tracemalloc_peak_mb = peak_size / (1024 * 1024)
            
        return MemoryStats(
            timestamp=time.time(),
            process_memory_mb=process_memory_mb,
            system_memory_percent=system_memory_percent,
            gc_collections=gc_stats,
            tracemalloc_current_mb=tracemalloc_current_mb,
            tracemalloc_peak_mb=tracemalloc_peak_mb
        )
        
    async def _handle_medium_memory(self, stats: MemoryStats):
        """Handle medium memory usage"""
        logger.info(f"Medium memory usage: {stats.process_memory_mb:.1f}MB")
        
        # Start more frequent monitoring
        # This is handled by the threshold level
        
    async def _handle_high_memory(self, stats: MemoryStats):
        """Handle high memory usage"""
        logger.warning(f"High memory usage: {stats.process_memory_mb:.1f}MB")
        
        # Trigger garbage collection
        collected = gc.collect()
        logger.info(f"Forced GC collected {collected} objects")
        
        # Clean managed buffers
        self._clean_managed_buffers()
        
        # Emit high memory event
        await self._emit_event("high_memory_usage", {
            "memory_mb": stats.process_memory_mb,
            "gc_collected": collected
        })
        
    async def _handle_critical_memory(self, stats: MemoryStats):
        """Handle critical memory usage"""
        logger.error(f"Critical memory usage: {stats.process_memory_mb:.1f}MB")
        
        # Aggressive cleanup
        collected = 0
        for i in range(3):  # Multiple GC passes
            collected += gc.collect()
            
        # Force clean all managed buffers
        self._emergency_buffer_cleanup()
        
        # Clear weak references
        self._cleanup_weak_references()
        
        # Emit critical memory event
        await self._emit_event("critical_memory_usage", {
            "memory_mb": stats.process_memory_mb,
            "gc_collected": collected,
            "action": "emergency_cleanup"
        })
        
        # Consider requesting restart if memory is still too high
        new_stats = self._get_memory_stats()
        if new_stats.process_memory_mb >= self.critical_threshold_mb * 0.9:
            await self._emit_event("restart_recommended", {
                "reason": "persistent_high_memory",
                "memory_mb": new_stats.process_memory_mb
            })
            
    def register_managed_buffer(
        self,
        buffer_name: str,
        buffer_object: List,
        max_size: Optional[int] = None
    ):
        """Register a buffer for memory management"""
        self._managed_buffers[buffer_name] = buffer_object
        
        if max_size:
            self.max_buffer_sizes[buffer_name] = max_size
            
        logger.debug(f"Registered managed buffer: {buffer_name}")
        
    def _clean_managed_buffers(self):
        """Clean managed buffers based on size limits"""
        for buffer_name, buffer_obj in self._managed_buffers.items():
            max_size = self.max_buffer_sizes.get(buffer_name)
            
            if max_size and len(buffer_obj) > max_size:
                # Keep only the most recent items
                items_to_remove = len(buffer_obj) - max_size
                if hasattr(buffer_obj, 'clear'):
                    # For deque or list-like objects
                    for _ in range(items_to_remove):
                        if buffer_obj:
                            buffer_obj.popleft() if hasattr(buffer_obj, 'popleft') else buffer_obj.pop(0)
                            
                logger.info(f"Cleaned buffer {buffer_name}: removed {items_to_remove} items")
                
    def _emergency_buffer_cleanup(self):
        """Emergency cleanup of all managed buffers"""
        for buffer_name, buffer_obj in self._managed_buffers.items():
            original_size = len(buffer_obj)
            
            # Clear half the buffer or reduce to max size, whichever is smaller
            max_size = self.max_buffer_sizes.get(buffer_name, len(buffer_obj) // 2)
            target_size = min(max_size, len(buffer_obj) // 2)
            
            while len(buffer_obj) > target_size and buffer_obj:
                if hasattr(buffer_obj, 'popleft'):
                    buffer_obj.popleft()
                else:
                    buffer_obj.pop(0)
                    
            cleaned_items = original_size - len(buffer_obj)
            if cleaned_items > 0:
                logger.warning(f"Emergency cleanup: {buffer_name} reduced by {cleaned_items} items")
                
    def track_object(self, obj: Any):
        """Track an object for leak detection"""
        try:
            weak_ref = weakref.ref(obj)
            self._tracked_objects.add(weak_ref)
        except TypeError:
            # Object doesn't support weak references
            pass
            
    def _cleanup_weak_references(self):
        """Clean up dead weak references"""
        dead_refs = {ref for ref in self._tracked_objects if ref() is None}
        self._tracked_objects -= dead_refs
        
        logger.debug(f"Cleaned up {len(dead_refs)} dead weak references")
        
    async def _take_baseline(self):
        """Take baseline measurement for leak detection"""
        if not tracemalloc.is_tracing():
            return
            
        # Wait a bit for initial allocations to settle
        await asyncio.sleep(5)
        
        self._baseline_objects = {}
        snapshot = tracemalloc.take_snapshot()
        
        # Group by filename for baseline
        for stat in snapshot.statistics('filename'):
            self._baseline_objects[stat.traceback.format()[-1]] = stat.size
            
        self._leak_detection_enabled = True
        logger.info("Established memory baseline for leak detection")
        
    async def _check_for_leaks(self):
        """Check for potential memory leaks"""
        if not self._leak_detection_enabled or not tracemalloc.is_tracing():
            return
            
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')
        
        # Find significant memory allocations
        significant_allocations = [
            stat for stat in top_stats[:10]
            if stat.size > 1024 * 1024  # > 1MB
        ]
        
        if significant_allocations:
            logger.debug("Top memory allocations:")
            for stat in significant_allocations[:5]:
                logger.debug(f"  {stat.traceback.format()[-1]}: {stat.size / 1024 / 1024:.1f}MB")
                
        # Look for growing allocations
        if len(self._memory_history) >= 5:
            recent_memory = [stats.tracemalloc_current_mb for stats in self._memory_history[-5:] if stats.tracemalloc_current_mb]
            if len(recent_memory) >= 5:
                # Check if memory is consistently growing
                is_growing = all(
                    recent_memory[i] <= recent_memory[i + 1]
                    for i in range(len(recent_memory) - 1)
                )
                
                if is_growing:
                    growth = recent_memory[-1] - recent_memory[0]
                    if growth > 50:  # Growing by more than 50MB
                        await self._emit_event("memory_leak_suspected", {
                            "growth_mb": growth,
                            "recent_memory_mb": recent_memory
                        })
                        logger.warning(f"Suspected memory leak: {growth:.1f}MB growth over recent checks")
                        
    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit memory guard events"""
        if self._event_emitter:
            event_data = {
                "service_name": self.service_name,
                **data
            }
            await self._event_emitter.emit(f"memory_{event_type}", event_data)
            
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics"""
        current_stats = self._get_memory_stats()
        
        # Calculate trends
        if len(self._memory_history) >= 2:
            prev_stats = self._memory_history[-2]
            memory_trend = current_stats.process_memory_mb - prev_stats.process_memory_mb
        else:
            memory_trend = 0.0
            
        return {
            "service_name": self.service_name,
            "current_memory_mb": current_stats.process_memory_mb,
            "memory_trend_mb": memory_trend,
            "threshold_level": current_stats.threshold_level.value,
            "system_memory_percent": current_stats.system_memory_percent,
            "managed_buffers": {
                name: len(buffer) for name, buffer in self._managed_buffers.items()
            },
            "gc_collections": current_stats.gc_collections,
            "tracked_objects": len(self._tracked_objects),
            "tracemalloc_enabled": tracemalloc.is_tracing(),
            "tracemalloc_current_mb": current_stats.tracemalloc_current_mb,
            "tracemalloc_peak_mb": current_stats.tracemalloc_peak_mb,
            "thresholds": {
                "medium_mb": self.medium_threshold_mb,
                "high_mb": self.high_threshold_mb,
                "critical_mb": self.critical_threshold_mb
            },
            "timestamp": current_stats.timestamp
        }
        
    def force_cleanup(self):
        """Force immediate cleanup"""
        logger.info("Forcing memory cleanup")
        
        # Garbage collection
        collected = 0
        for i in range(3):
            collected += gc.collect()
            
        # Clean buffers
        self._clean_managed_buffers()
        
        # Clean weak references
        self._cleanup_weak_references()
        
        logger.info(f"Forced cleanup completed: {collected} objects collected")
        
        return collected