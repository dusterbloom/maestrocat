"""
Speaker Context Processor

Enriches transcriptions with speaker information before they reach the LLM.
"""

import logging
from typing import Optional, Dict, Any
from pipecat.frames.frames import Frame, TranscriptionFrame, TextFrame, SystemFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

logger = logging.getLogger(__name__)


class SpeakerContextProcessor(FrameProcessor):
    """
    Adds speaker information to transcriptions so the LLM knows who's talking.
    
    This processor:
    1. Listens for speaker change events
    2. Intercepts transcriptions
    3. Enriches them with speaker context
    4. Optionally adds speaker info to the system prompt
    """
    
    def __init__(
        self,
        *,
        format_style: str = "natural",  # "natural", "prefix", "system"
        unknown_speaker_name: str = "User",
        name_manager=None,  # Optional SpeakerNameManager instance
        **kwargs
    ):
        """
        Initialize the speaker context processor.
        
        Args:
            format_style: How to format speaker info
                - "natural": Natural language in transcription
                - "prefix": [Speaker] prefix
                - "system": System message to LLM
            unknown_speaker_name: Name for unknown speakers
        """
        super().__init__(**kwargs)
        self.format_style = format_style
        self.unknown_speaker_name = unknown_speaker_name
        self.name_manager = name_manager
        self.current_speaker = None
        self.speaker_confidence = 0.0
        self.speaker_history = []  # Track speaker changes
        
    def set_event_emitter(self, event_emitter):
        """Connect to event emitter to receive speaker events"""
        self._event_emitter = event_emitter
        if event_emitter:
            # Subscribe to speaker events
            event_emitter.subscribe("speaker_changed", self._on_speaker_changed)
            event_emitter.subscribe("speaker_enrolled", self._on_speaker_enrolled)
            event_emitter.subscribe("known_speaker_returned", self._on_known_speaker_returned)
    
    async def _on_speaker_changed(self, event_data: Dict[str, Any]):
        """Handle speaker change events"""
        if isinstance(event_data, dict):
            data = event_data.get('data', event_data)
            self.current_speaker = data.get('speaker_name', 'unknown')
            self.speaker_confidence = data.get('confidence', 0.0)
            
            # Track history
            self.speaker_history.append({
                'speaker': self.current_speaker,
                'confidence': self.speaker_confidence,
                'timestamp': data.get('timestamp')
            })
            
            # Keep only last 10 changes
            if len(self.speaker_history) > 10:
                self.speaker_history.pop(0)
            
            logger.info(f"Speaker context updated: {self.current_speaker} (confidence: {self.speaker_confidence:.2f})")
            
            # If using system style, send a system message to LLM
            if self.format_style == "system" and self.current_speaker != "unknown":
                await self._send_speaker_system_message()
    
    async def _on_speaker_enrolled(self, event_data: Dict[str, Any]):
        """Handle speaker enrollment events"""
        if isinstance(event_data, dict):
            data = event_data.get('data', event_data)
            speaker_name = data.get('speaker_name', '')
            auto_enrolled = data.get('auto_enrolled', False)
            
            if auto_enrolled:
                logger.info(f"New speaker auto-enrolled: {speaker_name}")
                # Could send a system message about new speaker
    
    async def _on_known_speaker_returned(self, event_data: Dict[str, Any]):
        """Handle when a known speaker returns"""
        if isinstance(event_data, dict):
            data = event_data.get('data', event_data)
            speaker_id = data.get('speaker_id', '')
            real_name = data.get('real_name', '')
            
            if real_name:
                logger.info(f"✨ Known speaker returned: {real_name}")
                
                # Send a system message to the LLM
                # Create a transcription frame with system message that will be added to context
                system_message = f"[System: Recognized returning user - {real_name} is back]"
                # Use TranscriptionFrame so it gets aggregated into the LLM context
                from pipecat.frames.frames import TranscriptionFrame
                system_frame = TranscriptionFrame(
                    text=system_message,
                    user_id="system",
                    timestamp=data.get('timestamp')
                )
                
                await self.push_frame(system_frame)
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames, enriching transcriptions with speaker info"""
        await super().process_frame(frame, direction)
        
        # Intercept transcription frames
        if isinstance(frame, TranscriptionFrame):
            # Get speaker info
            speaker = self.current_speaker or "unknown"
            
            # Try to get real name if we have a name manager
            if self.name_manager and speaker != "unknown":
                real_name = self.name_manager.get_speaker_name(speaker)
                if real_name:
                    display_name = real_name
                elif speaker.startswith("Speaker_"):
                    display_name = f"Person {speaker.split('_')[1]}"
                else:
                    display_name = speaker
            else:
                display_name = speaker if speaker != "unknown" else self.unknown_speaker_name
            
            # Enrich transcription based on format style
            if self.format_style == "natural":
                # Natural language style - only add if we know the speaker
                if speaker != "unknown" and self.speaker_confidence > 0.7:
                    # Create a more natural format
                    if speaker.startswith("Speaker_"):
                        # For auto-enrolled speakers, use a friendly format
                        speaker_num = speaker.split("_")[1]
                        enriched_text = f"{frame.text}"
                        # Add context as metadata instead of modifying text
                        frame.metadata = frame.metadata or {}
                        frame.metadata['speaker'] = f"Person {speaker_num}"
                        frame.metadata['speaker_confidence'] = self.speaker_confidence
                    else:
                        # For named speakers
                        enriched_text = f"{frame.text}"
                        frame.metadata = frame.metadata or {}
                        frame.metadata['speaker'] = display_name
                        frame.metadata['speaker_confidence'] = self.speaker_confidence
                else:
                    enriched_text = frame.text
                    
            elif self.format_style == "prefix":
                # Prefix style - always add speaker
                if speaker.startswith("Speaker_"):
                    speaker_num = speaker.split("_")[1]
                    prefix = f"[Person {speaker_num}]"
                else:
                    prefix = f"[{display_name}]"
                enriched_text = f"{prefix} {frame.text}"
                
            else:  # system style
                # Don't modify transcription, context sent separately
                enriched_text = frame.text
            
            # Create new transcription frame with enriched text
            enriched_frame = TranscriptionFrame(
                text=enriched_text,
                user_id=frame.user_id,
                timestamp=frame.timestamp,
                language=frame.language
            )
            
            # Copy metadata
            if hasattr(frame, 'metadata'):
                enriched_frame.metadata = frame.metadata
            
            await self.push_frame(enriched_frame, direction)
        else:
            # Pass other frames through
            await self.push_frame(frame, direction)
    
    async def _send_speaker_system_message(self):
        """Send a system message about speaker change to LLM"""
        if self.current_speaker and self.current_speaker != "unknown":
            if self.current_speaker.startswith("Speaker_"):
                speaker_num = self.current_speaker.split("_")[1]
                message = f"[System: Now speaking with Person {speaker_num}]"
            else:
                message = f"[System: Now speaking with {self.current_speaker}]"
            
            # Create a text frame with system message for the LLM
            system_frame = TextFrame(text=message)
            
            await self.push_frame(system_frame)
    
    def get_speaker_summary(self) -> str:
        """Get a summary of recent speakers for context"""
        if not self.speaker_history:
            return "No speakers identified yet."
        
        unique_speakers = []
        for entry in reversed(self.speaker_history):
            speaker = entry['speaker']
            if speaker not in unique_speakers and speaker != "unknown":
                unique_speakers.append(speaker)
        
        if not unique_speakers:
            return "Speaking with unidentified users."
        
        if len(unique_speakers) == 1:
            speaker = unique_speakers[0]
            if speaker.startswith("Speaker_"):
                return f"Speaking with Person {speaker.split('_')[1]}."
            return f"Speaking with {speaker}."
        else:
            # Multiple speakers
            formatted = []
            for speaker in unique_speakers[:3]:  # Show up to 3 recent speakers
                if speaker.startswith("Speaker_"):
                    formatted.append(f"Person {speaker.split('_')[1]}")
                else:
                    formatted.append(speaker)
            return f"Recent speakers: {', '.join(formatted)}."