"""Voice recognition module for speaker identification and enrollment"""
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import asyncio
import threading
import queue
import time
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os

from ..processors.module_loader import MaestroCatModule
from pipecat.frames.frames import AudioRawFrame, InputAudioRawFrame, UserAudioRawFrame

logger = logging.getLogger(__name__)


@dataclass
class SpeakerProfile:
    """Represents a registered speaker"""
    id: str
    name: str
    embeddings: List[np.ndarray]
    created_at: datetime
    last_seen: Optional[datetime] = None
    confidence_threshold: float = 0.85


@dataclass
class SpeakerEvent:
    """Speaker identification event"""
    speaker_id: str
    speaker_name: str
    confidence: float
    timestamp: datetime
    event_type: str  # 'identified', 'changed', 'enrolled', 'unknown'


class VoiceRecognitionModule(MaestroCatModule):
    """
    Advanced voice recognition module with speaker identification.
    
    Features:
    - Real-time speaker identification from audio streams
    - Voice enrollment and profile management
    - Parallel audio processing without blocking STT
    - Confidence-based speaker changes
    - Persistent speaker profiles
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        
        # Configuration
        self.enabled = config.get('enabled', True)
        self.sample_rate = config.get('sample_rate', 16000)
        self.window_size = config.get('window_size', 3.0)  # seconds
        self.confidence_threshold = config.get('confidence_threshold', 0.85)
        self.min_speech_duration = config.get('min_speech_duration', 1.0)
        self.profile_dir = config.get('profile_dir', 'data/speaker_profiles')
        self.use_model = config.get('model', 'speechbrain')  # or 'pyannote'
        
        # Event emitter reference (will be set by ModuleLoader)
        self._event_emitter = None
        
        # Speaker management
        self.speakers: Dict[str, SpeakerProfile] = {}
        self.current_speaker: Optional[str] = None
        self.current_confidence: float = 0.0
        
        # Audio processing
        self.audio_buffer = deque(maxlen=int(self.sample_rate * self.window_size))
        self.processing_queue = queue.Queue(maxsize=100)
        self.processing_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Model placeholder (would load actual model)
        self.model = None
        self.embedding_size = 256  # typical size
        
        # Statistics
        self.total_identifications = 0
        self.speaker_changes = 0
        
    async def initialize(self):
        """Initialize the voice recognition module"""
        await super().initialize()
        
        if not self.enabled:
            logger.info("Voice recognition module disabled")
            return
            
        # Create profile directory
        os.makedirs(self.profile_dir, exist_ok=True)
        
        # Load saved speaker profiles
        await self._load_speaker_profiles()
        
        # Initialize model (mock for now)
        await self._initialize_model()
        
        # Start processing thread
        self.processing_thread = threading.Thread(
            target=self._processing_worker,
            daemon=True
        )
        self.processing_thread.start()
        
        logger.info(f"Voice recognition initialized with {len(self.speakers)} profiles")
    
    async def shutdown(self):
        """Cleanup resources"""
        self.stop_event.set()
        if self.processing_thread:
            self.processing_thread.join(timeout=5.0)
        await super().shutdown()
    
    async def on_event(self, event_type: str, data: Any):
        """Handle pipeline events"""
        if event_type == "transcription_complete" and self.current_speaker:
            # Attach speaker info to transcription
            data["speaker_id"] = self.current_speaker
            data["speaker_confidence"] = self.current_confidence
            
            # Update last seen time
            if self.current_speaker in self.speakers:
                self.speakers[self.current_speaker].last_seen = datetime.now()
    
    async def process_audio(self, frame: AudioRawFrame, sample_rate: int):
        """
        Process audio frame for speaker identification.
        Called by AudioTeeProcessor.
        """
        if not self.enabled:
            return
            
        try:
            # Convert audio to numpy array
            audio_data = np.frombuffer(frame.audio, dtype=np.int16)
            
            # Add to processing queue without blocking
            self.processing_queue.put_nowait({
                'audio': audio_data,
                'sample_rate': sample_rate,
                'timestamp': datetime.now()
            })
            
        except queue.Full:
            # Drop frame if queue is full to maintain real-time performance
            logger.debug("Voice recognition queue full, dropping frame")
                
    def _processing_worker(self):
        """Background thread for audio processing"""
        buffer = []
        last_process_time = time.time()
        
        while not self.stop_event.is_set():
            try:
                # Get audio from queue with timeout
                item = self.processing_queue.get(timeout=0.1)
                buffer.append(item['audio'])
                
                # Process when we have enough audio or timeout
                current_time = time.time()
                if (len(buffer) >= int(self.sample_rate * self.min_speech_duration / 1600) or
                    current_time - last_process_time > self.window_size):
                    
                    if buffer:
                        # Concatenate audio chunks
                        audio_chunk = np.concatenate(buffer)
                        
                        # Process for speaker identification
                        speaker_event = self._identify_speaker(audio_chunk)
                        
                        if speaker_event:
                            # Handle speaker change
                            asyncio.run_coroutine_threadsafe(
                                self._handle_speaker_event(speaker_event),
                                asyncio.get_event_loop()
                            )
                        
                        # Clear buffer
                        buffer = []
                        last_process_time = current_time
                        
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in voice processing: {e}")
    
    def _identify_speaker(self, audio_chunk: np.ndarray) -> Optional[SpeakerEvent]:
        """
        Identify speaker from audio chunk.
        Returns speaker event if identification is confident.
        """
        # Check if audio has sufficient energy
        energy = np.sqrt(np.mean(audio_chunk ** 2))
        if energy < 1000:  # Silence threshold
            return None
            
        # Extract embedding (mock implementation)
        embedding = self._extract_embedding(audio_chunk)
        
        # Compare with known speakers
        best_match = None
        best_confidence = 0.0
        
        for speaker_id, profile in self.speakers.items():
            confidence = self._compare_embeddings(embedding, profile.embeddings)
            
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = speaker_id
        
        # Check if we have a confident match
        timestamp = datetime.now()
        
        if best_match and best_confidence >= self.confidence_threshold:
            # Known speaker identified
            if best_match != self.current_speaker:
                self.speaker_changes += 1
                return SpeakerEvent(
                    speaker_id=best_match,
                    speaker_name=self.speakers[best_match].name,
                    confidence=best_confidence,
                    timestamp=timestamp,
                    event_type='changed'
                )
            return None  # Same speaker, no event
            
        elif best_confidence < 0.5:  # Very low confidence
            # Unknown speaker
            if self.current_speaker is not None:
                return SpeakerEvent(
                    speaker_id='unknown',
                    speaker_name='Unknown Speaker',
                    confidence=1.0 - best_confidence,
                    timestamp=timestamp,
                    event_type='unknown'
                )
        
        return None
    
    def _extract_embedding(self, audio: np.ndarray) -> np.ndarray:
        """
        Extract speaker embedding from audio.
        Mock implementation - would use actual model.
        """
        # Simulate embedding extraction
        # In production: use speechbrain, pyannote, or similar
        np.random.seed(int(np.sum(np.abs(audio[:100]))))
        return np.random.randn(self.embedding_size)
    
    def _compare_embeddings(self, embedding: np.ndarray, profile_embeddings: List[np.ndarray]) -> float:
        """
        Compare embedding with profile embeddings.
        Returns confidence score [0, 1].
        """
        if not profile_embeddings:
            return 0.0
            
        # Calculate cosine similarity with each profile embedding
        similarities = []
        for profile_emb in profile_embeddings:
            similarity = np.dot(embedding, profile_emb) / (
                np.linalg.norm(embedding) * np.linalg.norm(profile_emb)
            )
            similarities.append(similarity)
        
        # Return average similarity as confidence
        return np.mean(similarities)
    
    async def _handle_speaker_event(self, event: SpeakerEvent):
        """
        Handle speaker identification events.
        """
        self.current_speaker = event.speaker_id
        self.current_confidence = event.confidence
        self.total_identifications += 1
        
        # Emit event through the pipeline's event system
        event_data = {
            'speaker_id': event.speaker_id,
            'speaker_name': event.speaker_name,
            'confidence': event.confidence,
            'timestamp': event.timestamp.isoformat()
        }
        
        # Emit event if we have access to the event emitter
        if self._event_emitter:
            await self._event_emitter.emit(f'speaker_{event.event_type}', event_data)
        else:
            # Fallback logging if event emitter not available
            logger.info(f"Speaker event (no emitter): speaker_{event.event_type} - {event_data}")
        
        logger.info(
            f"Speaker {event.event_type}: {event.speaker_name} "
            f"(confidence: {event.confidence:.2f})"
        )
    
    async def enroll_speaker(self, name: str, audio_samples: List[np.ndarray]) -> str:
        """
        Enroll a new speaker with voice samples.
        
        Args:
            name: Speaker's name
            audio_samples: List of audio samples for enrollment
            
        Returns:
            speaker_id: Unique identifier for the speaker
        """
        # Generate unique speaker ID
        speaker_id = hashlib.md5(f"{name}_{datetime.now()}".encode()).hexdigest()[:8]
        
        # Extract embeddings from samples
        embeddings = []
        for audio in audio_samples:
            if len(audio) > self.sample_rate * 0.5:  # At least 0.5 seconds
                embedding = self._extract_embedding(audio)
                embeddings.append(embedding)
        
        if not embeddings:
            raise ValueError("No valid audio samples provided")
        
        # Create speaker profile
        profile = SpeakerProfile(
            id=speaker_id,
            name=name,
            embeddings=embeddings,
            created_at=datetime.now()
        )
        
        # Store profile
        self.speakers[speaker_id] = profile
        await self._save_speaker_profile(profile)
        
        # Emit enrollment event
        if self._event_emitter:
            await self._event_emitter.emit('speaker_enrolled', {
                'speaker_id': speaker_id,
                'speaker_name': name,
                'num_samples': len(embeddings)
            })
        
        logger.info(f"Enrolled speaker: {name} (ID: {speaker_id})")
        return speaker_id
    
    async def remove_speaker(self, speaker_id: str):
        """
        Remove a speaker profile.
        """
        if speaker_id in self.speakers:
            profile = self.speakers.pop(speaker_id)
            
            # Remove saved profile
            profile_path = os.path.join(self.profile_dir, f"{speaker_id}.json")
            if os.path.exists(profile_path):
                os.remove(profile_path)
            
            logger.info(f"Removed speaker: {profile.name} (ID: {speaker_id})")
    
    async def _initialize_model(self):
        """
        Initialize the speaker recognition model.
        Mock implementation - would load actual model.
        """
        # In production:
        # - Load speechbrain/pyannote model
        # - Configure device (CPU/GPU)
        # - Warm up model
        logger.info(f"Initialized mock speaker recognition model")
    
    async def _load_speaker_profiles(self):
        """
        Load saved speaker profiles from disk.
        """
        if not os.path.exists(self.profile_dir):
            return
            
        for filename in os.listdir(self.profile_dir):
            if filename.endswith('.json'):
                try:
                    filepath = os.path.join(self.profile_dir, filename)
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    
                    # Reconstruct profile
                    profile = SpeakerProfile(
                        id=data['id'],
                        name=data['name'],
                        embeddings=[np.array(emb) for emb in data['embeddings']],
                        created_at=datetime.fromisoformat(data['created_at']),
                        last_seen=datetime.fromisoformat(data['last_seen']) if data.get('last_seen') else None,
                        confidence_threshold=data.get('confidence_threshold', 0.85)
                    )
                    
                    self.speakers[profile.id] = profile
                    
                except Exception as e:
                    logger.error(f"Error loading profile {filename}: {e}")
    
    async def _save_speaker_profile(self, profile: SpeakerProfile):
        """
        Save speaker profile to disk.
        """
        filepath = os.path.join(self.profile_dir, f"{profile.id}.json")
        
        data = {
            'id': profile.id,
            'name': profile.name,
            'embeddings': [emb.tolist() for emb in profile.embeddings],
            'created_at': profile.created_at.isoformat(),
            'last_seen': profile.last_seen.isoformat() if profile.last_seen else None,
            'confidence_threshold': profile.confidence_threshold
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get module statistics.
        """
        return {
            'enabled': self.enabled,
            'num_profiles': len(self.speakers),
            'current_speaker': self.current_speaker,
            'current_confidence': self.current_confidence,
            'total_identifications': self.total_identifications,
            'speaker_changes': self.speaker_changes,
            'queue_size': self.processing_queue.qsize()
        }
