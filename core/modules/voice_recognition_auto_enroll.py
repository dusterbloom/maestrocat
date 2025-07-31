"""Automatic voice enrollment for magical speaker recognition"""
import numpy as np
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json
import os
import asyncio

from resemblyzer import VoiceEncoder
from .voice_recognition_lightweight import LightweightVoiceRecognition

logger = logging.getLogger(__name__)


class AutoEnrollVoiceRecognition(LightweightVoiceRecognition):
    """
    Voice recognition with automatic background enrollment.
    
    Magically learns voices as people speak without explicit enrollment!
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        
        # Auto-enrollment settings
        self.auto_enroll = config.get('auto_enroll', {})
        self.min_utterances = self.auto_enroll.get('min_utterances', 3)
        self.consistency_threshold = self.auto_enroll.get('consistency_threshold', 0.85)
        self.min_consistency_threshold = self.auto_enroll.get('min_consistency_threshold', 0.70)
        self.enrollment_window = self.auto_enroll.get('enrollment_window_minutes', 30)
        
        # Track unknown speakers with a session-based approach
        self.speaker_counter = 0
        self.current_unknown_fingerprints = []
        self.unknown_session_start_time = None

        # For dynamic thresholding after enrollment
        self.last_enrollment_time = None
        self.new_speaker_grace_period = timedelta(seconds=self.auto_enroll.get('new_speaker_grace_period_seconds', 60))
        self.new_speaker_similarity_threshold = self.auto_enroll.get('new_speaker_similarity_threshold', 0.65)
        
        # Initialize Resemblyzer VoiceEncoder
        # Explicitly use CPU to avoid GPU detection overhead on macOS
        self.encoder = VoiceEncoder("cpu")
        
        # Load any auto-enrolled profiles
        self._load_auto_profiles()
        
        # Load speaker name mappings
        self._load_speaker_names()
    
    def _process_speaker_identification(self, audio_array: np.ndarray):
        """Enhanced identification with auto-enrollment, processing a complete utterance."""
        try:
            fingerprint = self.encoder.embed_utterance(audio_array)
            fingerprint = np.nan_to_num(fingerprint)
            
            best_match = None
            best_similarity = 0
            
            for speaker_name, stored_fingerprints in self.speakers.items():
                for stored_fp in stored_fingerprints:
                    if fingerprint.shape != stored_fp.shape:
                        logger.warning(f"Skipping incompatible fingerprint for {speaker_name}.")
                        continue
                    similarity = self._calculate_similarity(fingerprint, stored_fp)
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = speaker_name
            
            if self.last_enrollment_time and (datetime.now() - self.last_enrollment_time) < self.new_speaker_grace_period:
                active_similarity_threshold = self.new_speaker_similarity_threshold
            else:
                active_similarity_threshold = self.similarity_threshold

            if best_match and best_similarity >= active_similarity_threshold:
                if best_match != self.current_speaker:
                    self.current_speaker = best_match
                    logger.info(f"🎯 Speaker recognized: {best_match} (confidence: {best_similarity:.2f})")
                    
                    # Check if we have a saved name for this speaker
                    if hasattr(self, 'speaker_names') and best_match in self.speaker_names:
                        real_name = self.speaker_names[best_match]
                        logger.info(f"✨ This is {real_name} returning!")
                        
                        # Emit a special event for known speakers returning
                        if self._event_emitter and hasattr(self, '_main_loop'):
                            asyncio.run_coroutine_threadsafe(
                                self._event_emitter.emit('known_speaker_returned', {
                                    'speaker_id': best_match,
                                    'real_name': real_name,
                                    'confidence': best_similarity,
                                    'timestamp': datetime.now().isoformat()
                                }),
                                self._main_loop
                            )
                    
                    self._emit_speaker_change(best_match, best_similarity)

                try:
                    stored_centroid = self.speakers[best_match][0]
                    alpha = 0.05
                    updated_centroid = (1 - alpha) * stored_centroid + alpha * fingerprint
                    updated_centroid /= np.linalg.norm(updated_centroid)
                    self.speakers[best_match][0] = updated_centroid
                    logger.debug(f"Adapted profile for {best_match} with new utterance.")
                except (IndexError, KeyError) as e:
                    logger.warning(f"Could not adapt profile for {best_match}: {e}")
            else:
                self._process_unknown_speaker(fingerprint)
                
        except Exception as e:
            logger.error(f"Error in speaker identification: {e}")
    
    def _process_unknown_speaker(self, fingerprint: np.ndarray):
        """Process unknown speaker for potential auto-enrollment using a session-based approach."""
        current_time = datetime.now()

        if self.unknown_session_start_time and (current_time - self.unknown_session_start_time) > timedelta(minutes=self.enrollment_window):
            self.current_unknown_fingerprints = []
            self.unknown_session_start_time = None

        if not self.current_unknown_fingerprints:
            self.current_unknown_fingerprints.append(fingerprint)
            self.unknown_session_start_time = current_time
            if self.current_speaker != "unknown":
                self.current_speaker = "unknown"
                logger.info("👤 Unknown speaker detected. Starting enrollment session.")
                self._emit_speaker_change("unknown", 0)
            return

        session_centroid = np.mean(self.current_unknown_fingerprints, axis=0)
        similarity = self._calculate_similarity(fingerprint, session_centroid)

        if similarity >= self.min_consistency_threshold:
            self.current_unknown_fingerprints.append(fingerprint)
            logger.debug(f"Collected {len(self.current_unknown_fingerprints)} consistent utterances for unknown speaker (similarity: {similarity:.2f}).")

            if len(self.current_unknown_fingerprints) >= self.min_utterances:
                self._auto_enroll_speaker(self.current_unknown_fingerprints)
                self.current_unknown_fingerprints = []
                self.unknown_session_start_time = None
        else:
            logger.warning(f"Inconsistent utterance from unknown speaker (similarity: {similarity:.2f} < {self.min_consistency_threshold}). Resetting session.")
            self.current_unknown_fingerprints = [fingerprint]
            self.unknown_session_start_time = current_time

    def _auto_enroll_speaker(self, fingerprints: List[np.ndarray]):
        """Automatically enroll a speaker after gathering enough consistent samples."""
        similarities = []
        for i in range(len(fingerprints)):
            for j in range(i + 1, len(fingerprints)):
                sim = self._calculate_similarity(fingerprints[i], fingerprints[j])
                similarities.append(sim)
        
        avg_consistency = np.mean(similarities) if similarities else 0
        
        if avg_consistency >= self.consistency_threshold:
            self.speaker_counter += 1
            speaker_name = f"Speaker_{self.speaker_counter}"
            
            centroid = np.mean(fingerprints, axis=0)
            centroid /= np.linalg.norm(centroid)

            self.speakers[speaker_name] = [centroid]
            self._save_auto_profile(speaker_name, [centroid])
            
            self.current_speaker = speaker_name
            self.last_enrollment_time = datetime.now()
            
            logger.info(f"✨ Magic! Auto-enrolled new speaker: {speaker_name}")
            logger.info(f"   Learned from {len(fingerprints)} utterances with {avg_consistency:.2f} consistency")
            
            if self._event_emitter:
                event_data = {
                    'speaker_id': speaker_name,
                    'speaker_name': speaker_name,
                    'auto_enrolled': True,
                    'num_samples': len(fingerprints),
                    'consistency': avg_consistency,
                    'timestamp': datetime.now().isoformat()
                }
                if hasattr(self, '_main_loop'):
                    import asyncio
                    asyncio.run_coroutine_threadsafe(
                        self._event_emitter.emit('speaker_enrolled', event_data),
                        self._main_loop
                    )
                    asyncio.run_coroutine_threadsafe(
                        self._event_emitter.emit('speaker_changed', {
                            'speaker_name': speaker_name,
                            'confidence': avg_consistency,
                            'timestamp': datetime.now().isoformat()
                        }),
                        self._main_loop
                    )
    
    def _calculate_similarity(self, fp1: np.ndarray, fp2: np.ndarray) -> float:
        """Calculate cosine similarity between fingerprints."""
        return np.dot(fp1, fp2)
    
    def _save_auto_profile(self, name: str, fingerprints: List[np.ndarray]):
        """Save auto-enrolled profile"""
        auto_dir = os.path.join(self.profile_dir, 'auto_enrolled')
        os.makedirs(auto_dir, exist_ok=True)
        
        filepath = os.path.join(auto_dir, f"{name}.json")
        data = {
            'name': name,
            'fingerprints': [fp.tolist() for fp in fingerprints],
            'auto_enrolled': True,
            'enrolled_at': datetime.now().isoformat()
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _load_auto_profiles(self):
        """Load auto-enrolled profiles"""
        auto_dir = os.path.join(self.profile_dir, 'auto_enrolled')
        if not os.path.exists(auto_dir):
            return
            
        for filename in os.listdir(auto_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(auto_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    
                    name = data['name']
                    fingerprints = [np.array(fp) for fp in data['fingerprints']]
                    self.speakers[name] = fingerprints
                    
                    if name.startswith('Speaker_'):
                        try:
                            num = int(name.split('_')[1])
                            self.speaker_counter = max(self.speaker_counter, num)
                        except:
                            pass
                    
                    logger.info(f"Loaded auto-enrolled profile: {name}")
                except Exception as e:
                    logger.error(f"Error loading auto profile {filename}: {e}")
    
    def _load_speaker_names(self):
        """Load speaker name mappings"""
        try:
            names_file = os.path.join(self.profile_dir, "speaker_names.json")
            if os.path.exists(names_file):
                with open(names_file, 'r') as f:
                    data = json.load(f)
                    self.speaker_names = data.get('mappings', {})
                    logger.info(f"Loaded {len(self.speaker_names)} speaker name mappings")
            else:
                self.speaker_names = {}
        except Exception as e:
            logger.error(f"Error loading speaker names: {e}")
            self.speaker_names = {}
