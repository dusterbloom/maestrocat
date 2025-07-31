"""Automatic voice enrollment for magical speaker recognition"""
import numpy as np
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import hashlib
import json
import os
from collections import defaultdict

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
        self.min_utterances = self.auto_enroll.get('min_utterances', 3)  # Need 3 utterances to create profile
        self.consistency_threshold = self.auto_enroll.get('consistency_threshold', 0.75)  # 75% similarity between samples
        self.enrollment_window = self.auto_enroll.get('enrollment_window_minutes', 30)  # 30 minute window
        
        # Track unknown speakers
        self.unknown_fingerprints = defaultdict(list)  # fingerprint_hash -> list of (fingerprint, timestamp)
        self.speaker_counter = 0
        
        # Load any auto-enrolled profiles
        self._load_auto_profiles()
        
        # Load speaker name mappings
        self._load_speaker_names()
    
    def _process_speaker_identification(self):
        """Enhanced identification with auto-enrollment"""
        try:
            # Convert buffer to array
            audio_array = np.array(list(self.audio_buffer))
            
            # Check audio energy
            energy = np.sqrt(np.mean(audio_array ** 2))
            if energy < 0.01:  # Silence threshold
                return
            
            # Extract MFCC features
            import librosa
            mfcc = librosa.feature.mfcc(
                y=audio_array, 
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
            
            # First, check against known speakers
            best_match = None
            best_similarity = 0
            
            for speaker_name, stored_fingerprints in self.speakers.items():
                for stored_fp in stored_fingerprints:
                    similarity = self._calculate_similarity(fingerprint, stored_fp)
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = speaker_name
            
            # Check if we have a known speaker match
            if best_match and best_similarity >= self.similarity_threshold:
                if best_match != self.current_speaker:
                    self.current_speaker = best_match
                    logger.info(f"🎯 Speaker recognized: {best_match} (confidence: {best_similarity:.2f})")
                    
                    # Check if this speaker has a real name
                    if hasattr(self, 'speaker_names') and best_match in self.speaker_names:
                        real_name = self.speaker_names[best_match]
                        logger.info(f"✨ This is {real_name}!")
                        
                        # Emit known speaker returned event
                        if self._event_emitter and hasattr(self, '_main_loop'):
                            import asyncio
                            asyncio.run_coroutine_threadsafe(
                                self._event_emitter.emit('known_speaker_returned', {
                                    'speaker_id': best_match,
                                    'real_name': real_name,
                                    'timestamp': datetime.now().isoformat()
                                }),
                                self._main_loop
                            )
                    
                    self._emit_speaker_change(best_match, best_similarity)
            else:
                # Unknown speaker - try auto-enrollment magic!
                self._process_unknown_speaker(fingerprint)
                
        except Exception as e:
            logger.error(f"Error in speaker identification: {e}")
    
    def _process_unknown_speaker(self, fingerprint: np.ndarray):
        """Process unknown speaker for potential auto-enrollment"""
        current_time = datetime.now()
        
        # Find which unknown speaker this might be
        best_unknown_match = None
        best_unknown_similarity = 0
        
        # Clean up old fingerprints outside enrollment window
        cutoff_time = current_time - timedelta(minutes=self.enrollment_window)
        
        for fp_hash in list(self.unknown_fingerprints.keys()):
            # Remove old entries
            self.unknown_fingerprints[fp_hash] = [
                (fp, ts) for fp, ts in self.unknown_fingerprints[fp_hash]
                if ts > cutoff_time
            ]
            
            # Remove empty entries
            if not self.unknown_fingerprints[fp_hash]:
                del self.unknown_fingerprints[fp_hash]
                continue
            
            # Check similarity with this unknown speaker's fingerprints
            similarities = []
            for stored_fp, _ in self.unknown_fingerprints[fp_hash]:
                sim = self._calculate_similarity(fingerprint, stored_fp)
                similarities.append(sim)
            
            avg_similarity = np.mean(similarities)
            if avg_similarity > best_unknown_similarity:
                best_unknown_similarity = avg_similarity
                best_unknown_match = fp_hash
        
        # Determine if this belongs to an existing unknown speaker or is new
        if best_unknown_match and best_unknown_similarity >= self.consistency_threshold:
            # Add to existing unknown speaker
            self.unknown_fingerprints[best_unknown_match].append((fingerprint, current_time))
            
            # Check if we have enough samples for auto-enrollment
            if len(self.unknown_fingerprints[best_unknown_match]) >= self.min_utterances:
                self._auto_enroll_speaker(best_unknown_match)
        else:
            # New unknown speaker
            fp_hash = hashlib.md5(fingerprint.tobytes()).hexdigest()[:8]
            self.unknown_fingerprints[fp_hash].append((fingerprint, current_time))
            
            if self.current_speaker != "unknown":
                self.current_speaker = "unknown"
                logger.info(f"👤 Unknown speaker detected")
                self._emit_speaker_change("unknown", 0)
    
    def _auto_enroll_speaker(self, fp_hash: str):
        """Automatically enroll a speaker after gathering enough consistent samples"""
        fingerprints = [fp for fp, _ in self.unknown_fingerprints[fp_hash]]
        
        # Verify consistency across all fingerprints
        similarities = []
        for i in range(len(fingerprints)):
            for j in range(i + 1, len(fingerprints)):
                sim = self._calculate_similarity(fingerprints[i], fingerprints[j])
                similarities.append(sim)
        
        avg_consistency = np.mean(similarities) if similarities else 0
        
        if avg_consistency >= self.consistency_threshold:
            # Create new speaker profile
            self.speaker_counter += 1
            speaker_name = f"Speaker_{self.speaker_counter}"
            
            # Store fingerprints
            self.speakers[speaker_name] = fingerprints
            
            # Save profile
            self._save_auto_profile(speaker_name, fingerprints)
            
            # Clean up unknown fingerprints
            del self.unknown_fingerprints[fp_hash]
            
            # Update current speaker
            self.current_speaker = speaker_name
            
            logger.info(f"✨ Magic! Auto-enrolled new speaker: {speaker_name}")
            logger.info(f"   Learned from {len(fingerprints)} utterances with {avg_consistency:.2f} consistency")
            
            # Emit enrollment event
            if self._event_emitter:
                event_data = {
                    'speaker_id': speaker_name,
                    'speaker_name': speaker_name,
                    'auto_enrolled': True,
                    'num_samples': len(fingerprints),
                    'consistency': avg_consistency,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Emit both enrollment and change events
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
        """Calculate cosine similarity between fingerprints"""
        import scipy.spatial.distance
        return 1 - scipy.spatial.distance.cosine(fp1, fp2)
    
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
                    
                    # Update speaker counter
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
                    for speaker_id, name in self.speaker_names.items():
                        logger.info(f"  {speaker_id} -> {name}")
            else:
                self.speaker_names = {}
        except Exception as e:
            logger.error(f"Error loading speaker names: {e}")
            self.speaker_names = {}