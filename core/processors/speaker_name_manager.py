"""
Speaker Name Manager

Allows the LLM to associate real names with voice profiles.
"""

import os
import json
import logging
import re
from typing import Dict, Optional, Any
from datetime import datetime
from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

logger = logging.getLogger(__name__)


class SpeakerNameManager(FrameProcessor):
    """
    Manages the association between speaker profiles and real names.
    
    Monitors LLM responses for name introductions and automatically
    updates speaker profiles with real names.
    """
    
    def __init__(
        self,
        profile_dir: str = "data/speaker_profiles",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.profile_dir = profile_dir
        self.names_file = os.path.join(profile_dir, "speaker_names.json")
        self.speaker_names = {}  # speaker_id -> real_name
        self.current_speaker = None
        self.waiting_for_name = False
        self.last_assistant_message = ""
        
        # Load existing name mappings
        self._load_names()
        
    def _load_names(self):
        """Load saved speaker name mappings"""
        try:
            if os.path.exists(self.names_file):
                with open(self.names_file, 'r') as f:
                    data = json.load(f)
                    self.speaker_names = data.get('mappings', {})
                    logger.info(f"Loaded {len(self.speaker_names)} speaker name mappings")
        except Exception as e:
            logger.error(f"Error loading speaker names: {e}")
    
    def _save_names(self):
        """Save speaker name mappings"""
        try:
            os.makedirs(self.profile_dir, exist_ok=True)
            data = {
                'mappings': self.speaker_names,
                'updated_at': datetime.now().isoformat()
            }
            with open(self.names_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving speaker names: {e}")
    
    def set_event_emitter(self, event_emitter):
        """Connect to event emitter"""
        self._event_emitter = event_emitter
        if event_emitter:
            event_emitter.subscribe("speaker_changed", self._on_speaker_changed)
            event_emitter.subscribe("speaker_enrolled", self._on_speaker_enrolled)
    
    async def _on_speaker_changed(self, event_data: Dict[str, Any]):
        """Track current speaker"""
        if isinstance(event_data, dict):
            data = event_data.get('data', event_data)
            self.current_speaker = data.get('speaker_name', 'unknown')
    
    async def _on_speaker_enrolled(self, event_data: Dict[str, Any]):
        """Handle new speaker enrollment"""
        if isinstance(event_data, dict):
            data = event_data.get('data', event_data)
            speaker_id = data.get('speaker_name', '')
            
            # Check if we already have a name for this speaker
            if speaker_id in self.speaker_names:
                real_name = self.speaker_names[speaker_id]
                logger.info(f"✨ Recognized returning user: {real_name}")
                
                # Emit an event so the LLM can be informed
                if self._event_emitter:
                    await self._event_emitter.emit('known_speaker_returned', {
                        'speaker_id': speaker_id,
                        'real_name': real_name,
                        'timestamp': datetime.now().isoformat()
                    })
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames to detect name introductions"""
        await super().process_frame(frame, direction)
        
        # Monitor assistant responses for name questions
        if isinstance(frame, TextFrame) and direction == FrameDirection.DOWNSTREAM:
            text = frame.text.lower()
            self.last_assistant_message = text
            
            # Log all assistant messages for debugging
            logger.debug(f"Assistant message: {text[:100]}...")
            
            # Detect if assistant is asking for a name
            name_patterns = [
                "what's your name",
                "what is your name", 
                "may i have your name",
                "can i get your name",
                "who am i speaking with",
                "who are you",
                "what should i call you",
                "how should i address you",
                "come ti chiami",  # Italian
                "qual è il tuo nome",  # Italian
                "comment tu t'appelles",  # French
                "quel est votre nom",  # French
                "como te llamas",  # Spanish
                "cuál es tu nombre",  # Spanish
                "qual é o seu nome",  # Portuguese
                "como você se chama"  # Portuguese
            ]
            
            if any(pattern in text for pattern in name_patterns):
                self.waiting_for_name = True
                logger.info(f"🎤 Assistant is asking for user's name (current speaker: {self.current_speaker})")
        
        # Monitor user responses for name introductions
        elif isinstance(frame, TranscriptionFrame) and self.waiting_for_name:
            text = frame.text
            logger.info(f"📝 User response while waiting for name: '{text}' (speaker: {self.current_speaker})")
            
            # Try to extract name from common patterns
            name = self._extract_name(text)
            
            if name and self.current_speaker and self.current_speaker != "unknown":
                # Associate the name with current speaker
                self.speaker_names[self.current_speaker] = name
                self._save_names()
                self.waiting_for_name = False
                
                logger.info(f"✨ Associated name '{name}' with {self.current_speaker}")
                logger.info(f"💾 Saved to speaker_names.json: {self.speaker_names}")
                
                # Update the frame metadata
                if not hasattr(frame, 'metadata'):
                    frame.metadata = {}
                frame.metadata['speaker_real_name'] = name
                
                # Emit event for other components
                if self._event_emitter:
                    await self._event_emitter.emit('speaker_name_learned', {
                        'speaker_id': self.current_speaker,
                        'real_name': name,
                        'timestamp': datetime.now().isoformat()
                    })
            else:
                logger.info(f"❓ Could not extract name from '{text}' or speaker is unknown")
        
        # Always pass frame through
        await self.push_frame(frame, direction)
    
    def _extract_name(self, text: str) -> Optional[str]:
        """Extract name from user response"""
        text = text.strip()
        logger.debug(f"Attempting to extract name from: '{text}'")
        
        # Common patterns for name introduction (case insensitive)
        patterns = [
            # English
            r"(?:my name is|i'm|i am|call me|it's|this is|I go by)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
            r"^([A-Za-z]+(?:\s+[A-Za-z]+)?)$",  # Just the name
            r"([A-Za-z]+(?:\s+[A-Za-z]+)?)\s+(?:here|speaking)",
            # Italian
            r"(?:mi chiamo|sono|chiamami)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
            # Add more language patterns as needed
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Capitalize properly
                name = ' '.join(word.capitalize() for word in name.split())
                if len(name) > 1 and len(name) < 50:  # Reasonable name length
                    logger.debug(f"Extracted name: '{name}' using pattern: {pattern}")
                    return name
        
        # If it's a short response (1-2 words), might just be the name
        words = text.split()
        if 1 <= len(words) <= 2:
            potential_name = ' '.join(word.capitalize() for word in words)
            # Check if it looks like a name (no numbers, reasonable characters)
            if potential_name and not any(char.isdigit() for char in potential_name):
                logger.debug(f"Extracted potential name from short response: '{potential_name}'")
                return potential_name
        
        logger.debug("No name found in text")
        return None
    
    def get_speaker_name(self, speaker_id: str) -> Optional[str]:
        """Get real name for a speaker ID"""
        return self.speaker_names.get(speaker_id)
    
    def get_all_known_names(self) -> Dict[str, str]:
        """Get all known speaker names"""
        return self.speaker_names.copy()