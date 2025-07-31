"""Lightweight voice recognition module using MFCC fingerprints"""
import numpy as np
import asyncio
import threading
import queue
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import deque
import pickle
import os

try:
    import librosa
    import scipy.spatial.distance
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    
from ..processors.module_loader import MaestroCatModule

logger = logging.getLogger(__name__)


class LightweightVoiceRecognition(MaestroCatModule):
    """
    Ultra-lightweight voice recognition using MFCC fingerprints.
    
    - No heavy ML models required
    - Sub-50ms processing time
    - Works entirely in background thread
    - Simple cosine similarity matching
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        
        # Configuration
        self.enabled = config.get('enabled', True) and LIBROSA_AVAILABLE
        self.sample_rate = 16000  # Fixed for consistency
        self.mfcc_features = 13  # Number of MFCC coefficients
        self.fingerprint_duration = 2.0  # Seconds of audio for fingerprint
        self.similarity_threshold = 0.85  # Cosine similarity threshold
        
        # Speaker database
        self.speakers = {}  # name -> mfcc_fingerprints list
        self.current_speaker = None
        
        # Audio processing
        self.audio_queue = queue.Queue(maxsize=100)
        self.processing_thread = None
        self.stop_event = threading.Event()
        
        # Buffer for accumulating audio
        self.audio_buffer = deque(maxlen=int(self.sample_rate * self.fingerprint_duration))
        
        # Event emitter reference
        self._event_emitter = None
        
        # Profile storage
        self.profile_dir = config.get('profile_dir', 'data/speaker_profiles')
        
    async def initialize(self):
        """Initialize the module"""
        await super().initialize()
        
        if not self.enabled:
            logger.warning("Lightweight voice recognition disabled (librosa not available)")
            return
            
        # Create profile directory
        os.makedirs(self.profile_dir, exist_ok=True)
        
        # Load saved profiles
        self._load_profiles()
        
        # Store event loop reference for thread communication
        self._main_loop = asyncio.get_running_loop()
        
        # Start processing thread
        self.processing_thread = threading.Thread(
            target=self._processing_worker,
            daemon=True
        )
        self.processing_thread.start()
        
        logger.info(f"Lightweight voice recognition initialized with {len(self.speakers)} profiles")
    
    async def process_audio(self, frame: Any, sample_rate: int):
        """Process audio frame for speaker identification"""
        if not self.enabled:
            return
            
        # Debug: Log first few audio frames
        if not hasattr(self, '_audio_frames_received'):
            self._audio_frames_received = 0
        self._audio_frames_received += 1
        if self._audio_frames_received <= 5:
            logger.info(f"🎤 Voice recognition received audio frame #{self._audio_frames_received}, size: {len(frame.audio)} bytes")
            
        try:
            # Convert audio to numpy array
            audio_data = np.frombuffer(frame.audio, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Resample if needed (fast)
            if sample_rate != self.sample_rate:
                # Simple decimation/interpolation
                ratio = self.sample_rate / sample_rate
                if ratio < 1:  # Downsample
                    indices = np.arange(0, len(audio_data), 1/ratio).astype(int)
                    audio_data = audio_data[indices[:int(len(audio_data) * ratio)]]
                else:  # Upsample (simple repeat)
                    audio_data = np.repeat(audio_data, int(ratio))
            
            # Add to queue without blocking
            self.audio_queue.put_nowait(audio_data)
            
        except queue.Full:
            # Drop frame to maintain real-time
            pass
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
    
    def _processing_worker(self):
        """Background thread for voice processing"""
        import time
        last_process_time = time.time()
        
        while not self.stop_event.is_set():
            try:
                # Collect audio chunks
                audio_chunk = self.audio_queue.get(timeout=0.1)
                self.audio_buffer.extend(audio_chunk)
                
                # Process every 0.5 seconds to reduce CPU load
                current_time = time.time()
                if current_time - last_process_time > 0.5:
                    buffer_size = len(self.audio_buffer)
                    logger.debug(f"Processing check: buffer size = {buffer_size}, required = {self.sample_rate * 0.5}")
                    if buffer_size >= self.sample_rate * 0.5:  # At least 0.5s of audio
                        # logger.info(f"🔍 Processing {buffer_size} audio samples for speaker identification")
                        self._process_speaker_identification()
                    last_process_time = current_time
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in processing worker: {e}")
    
    def _process_speaker_identification(self):
        """Identify speaker from buffered audio"""
        try:
            # Convert buffer to array
            audio_array = np.array(list(self.audio_buffer))
            
            # Check audio energy
            energy = np.sqrt(np.mean(audio_array ** 2))
            logger.debug(f"Processing audio with energy: {energy:.4f}")
            if energy < 0.01:  # Silence threshold
                logger.debug("Audio too quiet, skipping")
                return
            
            # Extract MFCC features (fast)
            mfcc = librosa.feature.mfcc(
                y=audio_array, 
                sr=self.sample_rate, 
                n_mfcc=self.mfcc_features,
                n_fft=512,  # Small FFT for speed
                hop_length=256
            )
            
            # Create fingerprint (mean and std of MFCCs)
            fingerprint = np.concatenate([
                np.mean(mfcc, axis=1),
                np.std(mfcc, axis=1)
            ])
            
            # Compare with known speakers
            best_match = None
            best_similarity = 0
            
            for speaker_name, stored_fingerprints in self.speakers.items():
                for stored_fp in stored_fingerprints:
                    # Cosine similarity (fast)
                    similarity = 1 - scipy.spatial.distance.cosine(fingerprint, stored_fp)
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = speaker_name
            
            # Check if we have a match
            if best_match and best_similarity >= self.similarity_threshold:
                if best_match != self.current_speaker:
                    self.current_speaker = best_match
                    logger.info(f"🎯 Speaker identified: {best_match} (confidence: {best_similarity:.2f})")
                    self._emit_speaker_change(best_match, best_similarity)
            else:
                # No match or low confidence - unknown speaker
                if self.current_speaker != "unknown":
                    self.current_speaker = "unknown"
                    logger.info(f"👤 Unknown speaker detected (best match: {best_match or 'none'}, confidence: {best_similarity:.2f})")
                    self._emit_speaker_change("unknown", 0)
                
        except Exception as e:
            logger.error(f"Error in speaker identification: {e}")
    
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
    
    async def enroll_speaker(self, name: str, audio_samples: List[np.ndarray]) -> bool:
        """Enroll a new speaker with audio samples"""
        if not self.enabled:
            return False
            
        try:
            fingerprints = []
            
            for audio in audio_samples:
                # Extract MFCC features
                mfcc = librosa.feature.mfcc(
                    y=audio, 
                    sr=self.sample_rate, 
                    n_mfcc=self.mfcc_features,
                    n_fft=512,
                    hop_length=256
                )
                
                # Create fingerprint
                fingerprint = np.concatenate([
                    np.mean(mfcc, axis=1),
                    np.std(mfcc, axis=1)
                ])
                
                fingerprints.append(fingerprint)
            
            # Store fingerprints
            self.speakers[name] = fingerprints
            
            # Save to disk
            self._save_profile(name, fingerprints)
            
            logger.info(f"Enrolled speaker: {name} with {len(fingerprints)} samples")
            return True
            
        except Exception as e:
            logger.error(f"Error enrolling speaker: {e}")
            return False
    
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
    
    async def on_event(self, event_data: Any):
        """Handle events from the pipeline"""
        # The event data is passed as a single argument containing type and data
        if isinstance(event_data, dict):
            event_type = event_data.get('type', '')
            data = event_data.get('data', {})
            # Log interesting events but don't process them
            if event_type in ['transcription_complete', 'llm_response_start']:
                logger.debug(f"Voice recognition received event: {event_type}")
    
    async def shutdown(self):
        """Cleanup"""
        self.stop_event.set()
        if self.processing_thread:
            self.processing_thread.join(timeout=1.0)
        await super().shutdown()