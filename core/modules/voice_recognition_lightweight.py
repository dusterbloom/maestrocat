"""
Base class for voice recognition modules.
This version uses an event-driven approach to process complete utterances,
which is more robust and suitable for libraries like Resemblyzer.
"""
import numpy as np
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import pickle
import os

from .base import MaestroCatModule

logger = logging.getLogger(__name__)

try:
    from resemblyzer import VoiceEncoder
    RESEMBLYZER_AVAILABLE = True
except ImportError:
    RESEMBLYZER_AVAILABLE = False

class LightweightVoiceRecognition(MaestroCatModule):
    """
    Base class for voice recognition. It buffers audio when the user is
    speaking and processes the complete utterance when they stop.
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        
        # Configuration
        self.enabled = config.get('enabled', True) and RESEMBLYZER_AVAILABLE
        self.sample_rate = 16000  # Fixed for consistency
        self.min_utterance_duration = config.get('min_utterance_duration_seconds', 1.0)
        self.similarity_threshold = config.get('confidence_threshold', 0.75)
        
        # Speaker database
        self.speakers = {}  # name -> fingerprints list
        self.current_speaker = None
        
        # Audio processing
        self.utterance_buffer = bytearray()
        self.is_speaking = False
        
        # Event emitter reference
        self._event_emitter = None
        
        # Profile storage
        self.profile_dir = config.get('profile_dir', 'data/speaker_profiles')
        
    async def initialize(self):
        """Initialize the module"""
        await super().initialize()
        
        if not self.enabled:
            logger.warning("Voice recognition disabled (Resemblyzer not available or disabled in config)")
            return
            
        os.makedirs(self.profile_dir, exist_ok=True)
        self._load_profiles()
        self._main_loop = asyncio.get_running_loop()
        logger.info(f"Lightweight voice recognition initialized with {len(self.speakers)} profiles")

    def set_event_emitter(self, event_emitter):
        """Connect to the application's event emitter to receive VAD events."""
        self._event_emitter = event_emitter
        if self._event_emitter:
            logger.info("Subscribing to user speaking events for voice recognition.")
            self._event_emitter.subscribe("user_started_speaking", self._on_user_started_speaking)
            self._event_emitter.subscribe("user_stopped_speaking", self._on_user_stopped_speaking)
    
    async def _on_user_started_speaking(self, event_data: Any):
        """Handle the start of a user utterance."""
        self.is_speaking = True
        self.utterance_buffer.clear()
        logger.debug("User started speaking, clearing utterance buffer for voice recognition.")

    async def _on_user_stopped_speaking(self, event_data: Any):
        """Handle the end of a user utterance and process it."""
        if not self.is_speaking:
            return
        
        self.is_speaking = False
        logger.debug(f"User stopped speaking. Processing {len(self.utterance_buffer)} bytes for speaker recognition.")
        
        utterance_duration = len(self.utterance_buffer) / (self.sample_rate * 2)
        if utterance_duration < self.min_utterance_duration:
            logger.info(f"Skipping speaker recognition for short utterance ({utterance_duration:.2f}s).")
            self.utterance_buffer.clear()
            return

        try:
            audio_array = np.frombuffer(self.utterance_buffer, dtype=np.int16).astype(np.float32) / 32768.0
            self._process_speaker_identification(audio_array)
        except Exception as e:
            logger.error(f"Error processing utterance for speaker recognition: {e}")
        finally:
            self.utterance_buffer.clear()
    
    async def process_audio(self, frame: Any, sample_rate: int):
        """Buffer audio frames when the user is speaking."""
        if self.enabled and self.is_speaking:
            self.utterance_buffer.extend(frame.audio)

    def _process_speaker_identification(self, audio_array: np.ndarray):
        """
        Placeholder for speaker identification.
        The actual implementation is in the AutoEnrollVoiceRecognition subclass.
        """
        logger.warning("Base class _process_speaker_identification called. Subclass should override this.")
        pass
    
    def _emit_speaker_change(self, speaker_name: str, confidence: float):
        """Emit speaker change event"""
        if self._event_emitter and hasattr(self, '_main_loop'):
            asyncio.run_coroutine_threadsafe(
                self._event_emitter.emit('speaker_changed', {
                    'speaker_name': speaker_name,
                    'confidence': confidence,
                    'timestamp': datetime.now().isoformat()
                }),
                self._main_loop
            )
        logger.info(f"Speaker changed to: {speaker_name} (confidence: {confidence:.2f})")

    def _save_profile(self, name: str, fingerprints: List[np.ndarray]):
        """Save speaker profile to disk"""
        filepath = os.path.join(self.profile_dir, f"{name}.pkl")
        with open(filepath, 'wb') as f:
            pickle.dump(fingerprints, f)
    
    def _load_profiles(self):
        """Load all speaker profiles from disk"""
        if not os.path.exists(self.profile_dir):
            return
            
        for filename in os.listdir(self.profile_dir):
            if filename.endswith('.pkl'):
                name = filename[:-4]
                filepath = os.path.join(self.profile_dir, filename)
                try:
                    with open(filepath, 'rb') as f:
                        fingerprints = pickle.load(f)
                    self.speakers[name] = fingerprints
                    logger.info(f"Loaded profile: {name}")
                except Exception as e:
                    logger.error(f"Error loading profile {name}: {e}")

    async def on_event(self, event_type: str, data: Any):
        """Handle events from the pipeline using standard MaestroCatModule interface."""
        # Voice recognition primarily works through audio processing, not events
        pass
        
    async def shutdown(self):
        """Cleanup if necessary."""
        await super().shutdown()