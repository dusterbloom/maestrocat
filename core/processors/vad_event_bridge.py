"""
VAD Event Bridge Processor

Converts Pipecat VAD frames (UserStartedSpeakingFrame/UserStoppedSpeakingFrame)
into MaestroCat event emitter events for modules to subscribe to.
"""

import logging
from typing import Optional
from pipecat.frames.frames import Frame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

logger = logging.getLogger(__name__)


class VADEventBridge(FrameProcessor):
    """
    Bridges Pipecat VAD frames to MaestroCat's event system.
    
    This processor watches for VAD frames in the pipeline and emits
    corresponding events through the event emitter, allowing modules
    like voice recognition to respond to voice activity.
    """
    
    def __init__(self, event_emitter=None, **kwargs):
        super().__init__(**kwargs)
        self._event_emitter = event_emitter
        self._user_speaking = False
        
    def set_event_emitter(self, event_emitter):
        """Set or update the event emitter."""
        self._event_emitter = event_emitter
        logger.info("VAD Event Bridge connected to event emitter")
        
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames and emit events for VAD frames."""
        await super().process_frame(frame, direction)
        
        # Convert VAD frames to events
        if isinstance(frame, UserStartedSpeakingFrame):
            if not self._user_speaking:
                self._user_speaking = True
                if self._event_emitter:
                    logger.debug("Emitting user_started_speaking event")
                    await self._event_emitter.emit("user_started_speaking", {
                        "timestamp": frame.timestamp if hasattr(frame, 'timestamp') else None
                    })
                    
        elif isinstance(frame, UserStoppedSpeakingFrame):
            if self._user_speaking:
                self._user_speaking = False
                if self._event_emitter:
                    logger.debug("Emitting user_stopped_speaking event")
                    await self._event_emitter.emit("user_stopped_speaking", {
                        "timestamp": frame.timestamp if hasattr(frame, 'timestamp') else None
                    })
        
        # Always pass the frame through
        await self.push_frame(frame, direction)