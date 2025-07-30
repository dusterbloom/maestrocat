# core/processors/transcription_events.py
"""Transcription event processor for emitting STT events to debug UI"""
import time
import logging
from typing import Optional

from pipecat.frames.frames import Frame, TranscriptionFrame, StartFrame, EndFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

logger = logging.getLogger(__name__)


class TranscriptionEventProcessor(FrameProcessor):
    """
    Processor that intercepts TranscriptionFrame objects and emits events for debug UI
    """
    
    def __init__(self, event_emitter=None):
        super().__init__()
        self._event_emitter = event_emitter
        
        # Deduplication tracking
        self._last_emitted_text = ""
        self._last_emission_time = 0.0
        self._dedup_time_window = 2.0  # 2 seconds window for deduplication
        
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames and emit events for transcription frames"""
        
        # Handle start/end frames properly
        if isinstance(frame, StartFrame):
            await super().process_frame(frame, direction)
            return
        elif isinstance(frame, EndFrame):
            await super().process_frame(frame, direction)
            return
        
        # Check if this is a transcription frame
        if isinstance(frame, TranscriptionFrame):
            if self._event_emitter and frame.text:
                current_time = time.time()
                
                # Check for duplicate emission (within time window)
                if (frame.text == self._last_emitted_text and 
                    current_time - self._last_emission_time < self._dedup_time_window):
                    logger.debug(f"🔇 BLOCKING DUPLICATE TRANSCRIPTION EVENT: '{frame.text}'")
                    # Still process the frame, just don't emit the event
                    await self.push_frame(frame, direction)
                    return
                
                # Track this emission for deduplication
                self._last_emitted_text = frame.text
                self._last_emission_time = current_time
                
                # Emit transcription event for debug UI
                await self._event_emitter.emit("transcription_final", {
                    "text": frame.text,
                    "confidence": 1.0,  # MLX Whisper doesn't provide confidence
                    "timestamp": current_time,
                    "user_id": frame.user_id or "user"
                })
                logger.debug(f"Emitted transcription event: '{frame.text}'")
        
        # Always pass the frame through
        await self.push_frame(frame, direction)