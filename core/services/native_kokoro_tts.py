# core/services/native_kokoro_tts_fixed.py
"""Native Kokoro ONNX TTS Service using the correct model and voices files"""
import asyncio
import time
import numpy as np
from typing import AsyncGenerator, Optional
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pipecat.frames.frames import Frame, TTSAudioRawFrame, TTSStartedFrame, TTSStoppedFrame, EndFrame
from pipecat.services.tts_service import TTSService

logger = logging.getLogger(__name__)


class NativeKokoroTTSService(TTSService):
    """
    Native Kokoro ONNX TTS service using the official kokoro-onnx library
    with correct model and voices files
    """
    
    def __init__(
        self,
        *,
        voice: str = "af_bella",
        speed: float = 1.0,
        sample_rate: int = 24000,
        event_emitter = None,
        **kwargs
    ):
        super().__init__(
            aggregate_sentences=True,  # Kokoro works best with full sentences
            **kwargs
        )
        
        self._voice = voice
        self._speed = speed
        self._sample_rate = sample_rate
        self._event_emitter = event_emitter
        self._language = None  # Will be determined from voice or config
        
        # Thread pool for non-blocking TTS generation
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kokoro-tts")
        
        # Initialize Kokoro ONNX pipeline
        self._pipeline = None
        self._initialize_pipeline()
        
        # Subscribe to config changes if event emitter is available
        if self._event_emitter:
            self._event_emitter.subscribe("config_change", self._handle_config_change)
            logger.info(f"✅ TTS service subscribed to config_change events")
        else:
            logger.warning(f"⚠️ TTS service initialized without event emitter - config changes will not work")
        
    def _ensure_models_downloaded(self):
        """Ensure the correct model and voices files are available"""
        cache_dir = Path.home() / ".cache" / "kokoro"
        model_path = cache_dir / "kokoro-v1.0.onnx"
        voices_path = cache_dir / "voices-v1.0.bin"
        
        # Check if files exist and are properly sized
        model_exists = model_path.exists() and model_path.stat().st_size > 300_000_000  # >300MB
        voices_exists = voices_path.exists() and voices_path.stat().st_size > 25_000_000  # >25MB
        
        if model_exists and voices_exists:
            return str(model_path), str(voices_path)
        
        # Files are missing - they should have been downloaded already
        raise FileNotFoundError(
            f"Kokoro model files not found!\n"
            f"Expected: {model_path} ({model_exists})\n"
            f"Expected: {voices_path} ({voices_exists})\n"
            f"Please run: python download_correct_kokoro.py\n"
            f"Or download manually from: https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0"
        )
        
    def _discover_available_voices(self):
        """Discover and map available voices from Kokoro"""
        if not self._pipeline:
            return {}
            
        # Common voice names to test
        test_voices = [
            # Italian voices
            'if_sara', 'im_nicola',
            # French voices  
            'ff_siwis',
            # English voices
            'af_bella', 'af_sarah', 'af_sky', 'af_alloy', 'af_nova', 'af_heart', 
            'am_adam', 'am_echo', 'am_michael', 'am_liam',
            # British English
            'bf_alice', 'bf_emma', 'bm_daniel', 'bm_george',
            # Other languages
            'jf_alpha', 'jm_kumo',  # Japanese
            'zf_xiaobei', 'zm_yunxi',  # Chinese
            'pf_dora', 'pm_alex'  # Portuguese
        ]
        
        available_voices = {}
        
        # Test numeric indices (fallback method)
        for i in range(30):  # Test first 30 voice indices
            try:
                test_audio, _ = self._pipeline.create("Test", voice=i, speed=1.0)
                if test_audio is not None and len(test_audio) > 100:
                    available_voices[f"voice_{i}"] = i
                    logger.debug(f"✅ Voice index {i} available")
            except:
                continue
        
        # Test named voices
        for voice_name in test_voices:
            try:
                test_audio, _ = self._pipeline.create("Test", voice=voice_name, speed=1.0)
                if test_audio is not None and len(test_audio) > 100:
                    available_voices[voice_name] = voice_name
                    logger.debug(f"✅ Named voice '{voice_name}' available")
            except:
                logger.debug(f"❌ Named voice '{voice_name}' not available")
                continue
        
        logger.info(f"🎯 Discovered {len(available_voices)} available voices: {list(available_voices.keys())}")
        return available_voices

    def _get_voice_language_mapping(self):
        """Map voice names to their respective languages"""
        return {
            # Italian
            'if_sara': 'it', 'im_nicola': 'it',
            # French
            'ff_siwis': 'fr',
            # English (US)
            'af_bella': 'en', 'af_sarah': 'en', 'af_sky': 'en', 'af_alloy': 'en', 
            'af_nova': 'en', 'af_heart': 'en', 'af_jessica': 'en', 'af_kore': 'en',
            'af_nicole': 'en', 'af_river': 'en', 'af_aoede': 'en',
            'am_adam': 'en', 'am_echo': 'en', 'am_michael': 'en', 'am_liam': 'en',
            'am_eric': 'en', 'am_fenrir': 'en', 'am_onyx': 'en', 'am_puck': 'en',
            # English (UK)
            'bf_alice': 'en', 'bf_emma': 'en', 'bf_isabella': 'en', 'bf_lily': 'en',
            'bm_daniel': 'en', 'bm_george': 'en', 'bm_lewis': 'en', 'bm_fable': 'en',
            # Japanese
            'jf_alpha': 'ja', 'jf_gongitsune': 'ja', 'jf_nezumi': 'ja', 'jf_tebukuro': 'ja',
            'jm_kumo': 'ja',
            # Chinese
            'zf_xiaobei': 'zh', 'zf_xiaoni': 'zh', 'zf_xiaoxiao': 'zh', 'zf_xiaoyi': 'zh',
            'zm_yunxi': 'zh', 'zm_yunxia': 'zh', 'zm_yunyang': 'zh', 'zm_yunjian': 'zh',
            # Portuguese
            'pf_dora': 'pt', 'pm_alex': 'pt', 'pm_santa': 'pt'
        }

    def _get_language_from_voice(self, voice_name):
        """Get the language code for a given voice"""
        voice_lang_map = self._get_voice_language_mapping()
        return voice_lang_map.get(voice_name, 'en')  # Default to English

    def _get_kokoro_language_code(self, lang_code):
        """Convert our language codes to Kokoro's expected language codes"""
        # Based on Kokoro-ONNX documentation - uses full language codes
        kokoro_lang_map = {
            'en': 'en-us',  # American English 
            'it': 'it',     # Italian
            'fr': 'fr-fr',  # French
            'es': 'es',     # Spanish
            'ja': 'ja',     # Japanese
            'zh': 'zh',     # Mandarin Chinese
            'pt': 'pt-br',  # Portuguese (Brazilian)
        }
        return kokoro_lang_map.get(lang_code, 'en-us')  # Default to American English

    def _validate_and_map_voice(self, requested_voice):
        """Validate and map a requested voice to an available one"""
        if not hasattr(self, '_available_voices'):
            return requested_voice, False
            
        # Direct match
        if requested_voice in self._available_voices:
            logger.debug(f"✅ Direct voice match: {requested_voice}")
            return self._available_voices[requested_voice], True
            
        # Try to find a voice of the same language
        voice_lang_map = self._get_voice_language_mapping()
        requested_lang = voice_lang_map.get(requested_voice)
        
        if requested_lang:
            # Find available voices of the same language
            available_same_lang = [
                v for v in self._available_voices.keys() 
                if voice_lang_map.get(v) == requested_lang
            ]
            
            if available_same_lang:
                fallback_voice = available_same_lang[0]  # Use first available
                mapped_voice = self._available_voices[fallback_voice]
                logger.info(f"🔄 Voice mapping: {requested_voice} -> {fallback_voice} (same language: {requested_lang})")
                return mapped_voice, True
        
        # Ultimate fallback to first available voice
        if self._available_voices:
            fallback_name = list(self._available_voices.keys())[0]
            fallback_voice = self._available_voices[fallback_name]
            logger.warning(f"⚠️ Voice fallback: {requested_voice} -> {fallback_name} (no language match)")
            return fallback_voice, False
            
        logger.error(f"❌ No voices available, using original: {requested_voice}")
        return requested_voice, False

    def _initialize_pipeline(self):
        """Initialize the Kokoro ONNX pipeline"""
        try:
            from kokoro_onnx import Kokoro
            
            logger.info(f"🚀 Initializing native Kokoro ONNX TTS with voice: {self._voice}")
            
            # Ensure models are available
            model_path, voices_path = self._ensure_models_downloaded()
            
            logger.info(f"Using model: {model_path}")
            logger.info(f"Using voices: {voices_path}")
            
            # Initialize Kokoro with the correct files
            self._pipeline = Kokoro(
                model_path=model_path,
                voices_path=voices_path,
                espeak_config=None  # Use default
            )
            
            logger.info(f"✅ Kokoro pipeline loaded successfully")
            
            # Discover available voices
            self._available_voices = self._discover_available_voices()
            
            # Validate and map the initial voice
            mapped_voice, is_exact_match = self._validate_and_map_voice(self._voice)
            if not is_exact_match:
                logger.warning(f"⚠️ Initial voice '{self._voice}' not available, using: {mapped_voice}")
            
            # Test the mapped voice
            try:
                test_audio, test_sr = self._pipeline.create("Hello", voice=mapped_voice, speed=self._speed)
                logger.info(f"✅ Voice '{mapped_voice}' verified - generated {len(test_audio)} samples at {test_sr}Hz")
                # Store the working voice
                self._working_voice = mapped_voice
            except Exception as voice_error:
                logger.error(f"❌ Even mapped voice '{mapped_voice}' failed: {voice_error}")
                # Try safe fallback voice
                try:
                    test_audio, test_sr = self._pipeline.create("Hello", voice="af_bella", speed=self._speed)
                    logger.info(f"✅ Fallback to af_bella - generated {len(test_audio)} samples")
                    self._working_voice = "af_bella"
                except:
                    # Last resort: try voice 0 as string
                    test_audio, test_sr = self._pipeline.create("Hello", voice="0", speed=self._speed)
                    logger.info(f"✅ Ultimate fallback to voice 0 - generated {len(test_audio)} samples")
                    self._working_voice = "0"
            
            logger.info("✅ Native Kokoro ONNX TTS initialized and warmed up")
            
            # Store flag to emit voices info later when we have async context
            self._should_emit_voices = True
            
        except ImportError:
            logger.error("kokoro-onnx not installed. Install with: pip install kokoro-onnx")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to initialize Kokoro ONNX: {e}")
            self._pipeline = None
            raise
    
    async def _handle_config_change(self, event: dict):
        """Handle configuration change events"""
        # Extract data from event structure
        event_data = event.get("data", {})
        component = event_data.get("component")
        settings = event_data.get("settings", {})
        
        logger.info(f"🎛️ TTS config change received: component={component}, settings={settings}")
        
        if component == "tts" and "voice" in settings:
            new_voice = settings["voice"]
            if new_voice != self._voice:
                logger.info(f"🔄 TTS voice change requested: {self._voice} -> {new_voice}")
                old_voice = self._voice
                
                # Validate and map the new voice
                if hasattr(self, '_available_voices'):
                    mapped_voice, is_exact_match = self._validate_and_map_voice(new_voice)
                    
                    # Test the new voice before applying
                    try:
                        test_audio, _ = self._pipeline.create("Test", voice=mapped_voice, speed=self._speed)
                        if test_audio is not None and len(test_audio) > 100:
                            # Voice works, apply the change
                            self._voice = new_voice
                            self._working_voice = mapped_voice
                            
                            # Update language based on the new voice
                            self._language = self._get_language_from_voice(new_voice)
                            
                            status = "exact_match" if is_exact_match else "mapped"
                            logger.info(f"✅ Voice successfully changed to {new_voice} -> {mapped_voice} ({status})")
                            logger.info(f"🌍 Language updated to: {self._language}")
                            
                            # Emit success event
                            if self._event_emitter:
                                await self._event_emitter.emit("tts_voice_changed", {
                                    "old_voice": old_voice,
                                    "new_voice": new_voice,
                                    "mapped_voice": str(mapped_voice),
                                    "status": status,
                                    "success": True,
                                    "timestamp": time.time()
                                })
                        else:
                            raise Exception("Voice test failed - no audio generated")
                            
                    except Exception as e:
                        logger.error(f"❌ Voice change failed for {new_voice} -> {mapped_voice}: {e}")
                        
                        # Emit failure event
                        if self._event_emitter:
                            await self._event_emitter.emit("tts_voice_changed", {
                                "old_voice": old_voice,
                                "new_voice": new_voice,
                                "mapped_voice": str(mapped_voice),
                                "status": "failed",
                                "success": False,
                                "error": str(e),
                                "timestamp": time.time()
                            })
                else:
                    # No voice discovery available, apply directly
                    self._voice = new_voice
                    logger.warning(f"⚠️ Voice changed to {new_voice} without validation (discovery not available)")
                    
                    if self._event_emitter:
                        await self._event_emitter.emit("tts_voice_changed", {
                            "old_voice": old_voice,
                            "new_voice": new_voice,
                            "status": "unvalidated",
                            "success": True,
                            "timestamp": time.time()
                        })
        
        # Handle speed changes
        if component == "tts" and "speed" in settings:
            new_speed = settings["speed"]
            if new_speed != self._speed:
                logger.info(f"🔄 TTS speed changed from {self._speed} to {new_speed}")
                self._speed = new_speed
    
    def _generate_audio_sync(self, text: str) -> Optional[tuple[np.ndarray, int]]:
        """Synchronous audio generation - runs in thread pool"""
        if not self._pipeline:
            logger.error("Kokoro pipeline not initialized")
            return None
            
        try:
            start_time = time.time()
            
            # Use the working voice if available, otherwise try to validate current voice
            voice_to_use = getattr(self, '_working_voice', self._voice)
            
            # Determine language for proper pronunciation
            voice_language = self._language or self._get_language_from_voice(str(voice_to_use))
            kokoro_lang = self._get_kokoro_language_code(voice_language)
            
            # Generate audio using Kokoro ONNX
            try:
                # Try with language parameter first (if supported)
                try:
                    audio_data, sample_rate = self._pipeline.create(
                        text, 
                        voice=voice_to_use, 
                        speed=self._speed,
                        lang=kokoro_lang
                    )
                    logger.debug(f"✅ Generated audio with voice: {voice_to_use}, language: {kokoro_lang} ({voice_language})")
                    
                except TypeError:
                    # Fallback without language parameter if not supported
                    audio_data, sample_rate = self._pipeline.create(text, voice=voice_to_use, speed=self._speed)
                    logger.debug(f"✅ Generated audio with voice: {voice_to_use} (no language param)")
                
            except Exception as voice_error:
                logger.warning(f"❌ Voice '{voice_to_use}' failed: {voice_error}")
                
                # Try to re-validate and map the voice
                if hasattr(self, '_available_voices'):
                    mapped_voice, _ = self._validate_and_map_voice(self._voice)
                    try:
                        # Try with language parameter
                        try:
                            audio_data, sample_rate = self._pipeline.create(
                                text, 
                                voice=mapped_voice, 
                                speed=self._speed,
                                lang=kokoro_lang
                            )
                        except TypeError:
                            audio_data, sample_rate = self._pipeline.create(text, voice=mapped_voice, speed=self._speed)
                        
                        logger.info(f"✅ Recovered with mapped voice: {mapped_voice}")
                        self._working_voice = mapped_voice
                        
                    except Exception as fallback_error:
                        # Ultimate fallback to a safe voice name
                        logger.warning(f"⚠️ Mapped voice failed: {fallback_error}, falling back to af_bella")
                        try:
                            audio_data, sample_rate = self._pipeline.create(text, voice="af_bella", speed=self._speed)
                            self._working_voice = "af_bella"
                        except:
                            # Last resort: try voice index 0 as string
                            logger.warning(f"⚠️ Even af_bella failed, trying voice 0")
                            audio_data, sample_rate = self._pipeline.create(text, voice="0", speed=self._speed)
                            self._working_voice = "0"
                else:
                    # Fallback to a safe voice name
                    logger.warning(f"⚠️ No voice discovery, falling back to af_bella")
                    try:
                        audio_data, sample_rate = self._pipeline.create(text, voice="af_bella", speed=self._speed)
                        self._working_voice = "af_bella"
                    except:
                        logger.warning(f"⚠️ Even af_bella failed, trying voice 0 as string")
                        audio_data, sample_rate = self._pipeline.create(text, voice="0", speed=self._speed)
                        self._working_voice = "0"
            
            generation_time = time.time() - start_time
            
            # Log performance and voice info
            chars_per_sec = len(text) / generation_time if generation_time > 0 else 0
            logger.debug(f"Generated {len(text)} chars in {generation_time:.3f}s ({chars_per_sec:.1f} chars/s) with voice: {voice_to_use}")
            
            return audio_data, sample_rate
            
        except Exception as e:
            logger.error(f"Kokoro TTS generation failed: {e}")
            return None
    
    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """Generate speech from text using native Kokoro ONNX"""
        
        if not text.strip():
            return
            
        logger.debug(f"Generating TTS for: '{text[:50]}{'...' if len(text) > 50 else ''}'")
        
        # Start timing
        tts_start_time = time.time()
        
        # Emit available voices info on first run
        if hasattr(self, '_should_emit_voices') and self._should_emit_voices and self._event_emitter:
            available_voices = self.get_available_voices()
            await self._event_emitter.emit("tts_voices_discovered", {
                "voices": available_voices,
                "total_count": len(available_voices),
                "timestamp": time.time()
            })
            self._should_emit_voices = False
            logger.info(f"📢 Emitted {len(available_voices)} available voices to UI")

        # Emit TTS start event
        voice_to_report = getattr(self, '_working_voice', self._voice)
        if self._event_emitter:
            await self._event_emitter.emit("tts_audio_start", {
                "text": text,
                "voice": str(voice_to_report),
                "requested_voice": self._voice,
                "timestamp": time.time()
            })
        
        yield TTSStartedFrame()
        
        try:
            # Run TTS generation in thread pool to avoid blocking
            result = await asyncio.get_event_loop().run_in_executor(
                self._executor,
                self._generate_audio_sync,
                text
            )
            
            # Calculate TTS latency to audio ready (not generation complete)
            tts_latency = (time.time() - tts_start_time) * 1000  # Convert to milliseconds
            
            # Emit timing metrics immediately when audio is ready to play
            if self._event_emitter:
                await self._event_emitter.emit("metrics_update", {
                    "stt_latency_ms": 0.0,  # Will be updated by STT service
                    "llm_latency_ms": 0.0,  # Will be updated by LLM service
                    "tts_latency_ms": tts_latency,
                    "total_latency_ms": tts_latency,
                    "timestamp": time.time(),
                    "component": "tts"
                })
                logger.info(f"📊 Emitted TTS metrics: {tts_latency:.1f}ms")
            
            if result is not None:
                audio_data, actual_sample_rate = result
                
                if audio_data is not None and len(audio_data) > 0:
                    # Convert to int16 for Pipecat
                    if audio_data.dtype != np.int16:
                        # Kokoro returns float32, convert to int16
                        audio_int16 = (audio_data * 32767).astype(np.int16)
                    else:
                        audio_int16 = audio_data
                    
                    # Create audio frame with actual sample rate from Kokoro
                    frame = TTSAudioRawFrame(
                        audio=audio_int16.tobytes(),
                        sample_rate=actual_sample_rate,
                        num_channels=1
                    )
                    
                    yield frame
                    
                    # Emit TTS complete event
                    if self._event_emitter:
                        await self._event_emitter.emit("tts_audio_complete", {
                            "text": text,
                            "voice": str(voice_to_report),
                            "requested_voice": self._voice,
                            "audio_length_bytes": len(audio_int16.tobytes()),
                            "timestamp": time.time()
                        })
                
            else:
                logger.warning("No audio data generated")
                
        except asyncio.CancelledError:
            logger.info("Native Kokoro TTS cancelled")
            raise
        except Exception as e:
            logger.error(f"Native Kokoro TTS error: {e}")
        finally:
            yield TTSStoppedFrame()
    
    def get_available_voices(self):
        """Get the discovered available voices"""
        if hasattr(self, '_available_voices'):
            voice_lang_map = self._get_voice_language_mapping()
            
            # Format voices for UI consumption
            formatted_voices = []
            for voice_name, voice_id in self._available_voices.items():
                if not voice_name.startswith('voice_'):  # Skip numeric indices
                    lang = voice_lang_map.get(voice_name, 'unknown')
                    formatted_voices.append({
                        'id': voice_name,
                        'name': voice_name.replace('_', ' ').title(),
                        'lang': lang,
                        'available': True
                    })
            
            return sorted(formatted_voices, key=lambda x: (x['lang'], x['name']))
        
        return []

    async def stop(self, frame=None):
        """Cleanup resources"""
        logger.info("Stopping Native Kokoro TTS Service")
        
        # Shutdown thread pool
        if self._executor:
            self._executor.shutdown(wait=True)
            
        if frame:
            await super().stop(frame)
        else:
            # TTSService.stop() expects a frame parameter in newer versions
            await super().stop(EndFrame())