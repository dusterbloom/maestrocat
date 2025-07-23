# maestrocat/processors/event_emitter.py
"""Enhanced event system for Pipecat pipelines"""
import asyncio
from typing import Dict, Any, List, Optional, Callable
from collections import defaultdict, deque
import time
import logging

from pipecat.frames.frames import Frame, SystemFrame, TextFrame, StartFrame, EndFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

logger = logging.getLogger(__name__)


class EventEmitter(FrameProcessor):
    """
    Enhanced event system that extends Pipecat's frame system
    Provides pub/sub, event history, and filtering
    """
    
    def __init__(
        self,
        buffer_size: int = 1000,
        emit_as_frames: bool = True
    ):
        super().__init__()
        self.buffer_size = buffer_size
        self.emit_as_frames = emit_as_frames
        
        # Event handling
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._event_buffer = deque(maxlen=buffer_size)
        self._event_count = 0
        
    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to an event type"""
        self._subscribers[event_type].append(callback)
        
    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribe from an event type"""
        if callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
            
    async def emit(self, event_type: str, data: Any):
        """Emit an event"""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
            "id": self._event_count
        }
        
        self._event_count += 1
        self._event_buffer.append(event)
        
        # Call subscribers
        for callback in self._subscribers[event_type]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")
                
        # Emit as frame if enabled
        if self.emit_as_frames:
            # Use TextFrame to carry event data as JSON
            import json
            event_data = json.dumps({"type": event_type, "data": data})
            await self.push_frame(TextFrame(event_data))
            
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Convert certain frames to events"""
        # Handle StartFrame/EndFrame properly
        if isinstance(frame, StartFrame):
            await self.emit("pipeline_started", {})
        elif isinstance(frame, EndFrame):
            await self.emit("pipeline_ended", {})
        elif isinstance(frame, SystemFrame):
            # Convert system frames to events
            await self.emit(frame.name, getattr(frame, 'data', {}))
            
        # Always pass the frame through
        await self.push_frame(frame, direction)
        
    def get_event_history(
        self,
        event_type: Optional[str] = None,
        since_timestamp: Optional[float] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get event history with optional filtering"""
        events = list(self._event_buffer)
        
        # Filter by type
        if event_type:
            events = [e for e in events if e["type"] == event_type]
            
        # Filter by timestamp
        if since_timestamp:
            events = [e for e in events if e["timestamp"] > since_timestamp]
            
        # Limit results
        if limit:
            events = events[-limit:]
            
        return events
