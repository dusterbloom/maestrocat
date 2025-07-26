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
        
        # Thread pool for non-blocking TTS generation
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kokoro-tts")
        
        # Initialize Kokoro ONNX pipeline
        self._pipeline = None
        self._initialize_pipeline()
        
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
            
            logger.info(f"✅ Loaded voices successfully")
            
            # Test voice availability
            try:
                test_audio, test_sr = self._pipeline.create("Hello", voice=self._voice, speed=self._speed)
                logger.info(f"✅ Voice '{self._voice}' verified - generated {len(test_audio)} samples at {test_sr}Hz")
            except Exception as voice_error:
                logger.warning(f"Voice '{self._voice}' not available: {voice_error}")
                logger.info("Available voices: Check the voices file or use a different voice name")
                # Try with a simple voice index instead
                test_audio, test_sr = self._pipeline.create("Hello", voice=0, speed=self._speed)
                logger.info(f"✅ Fallback to voice index 0 - generated {len(test_audio)} samples")
            
            logger.info("✅ Native Kokoro ONNX TTS initialized and warmed up")
            
        except ImportError:
            logger.error("kokoro-onnx not installed. Install with: pip install kokoro-onnx")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to initialize Kokoro ONNX: {e}")
            self._pipeline = None
            raise
    
    def _generate_audio_sync(self, text: str) -> Optional[tuple[np.ndarray, int]]:
        """Synchronous audio generation - runs in thread pool"""
        if not self._pipeline:
            logger.error("Kokoro pipeline not initialized")
            return None
            
        try:
            start_time = time.time()
            
            # Generate audio using Kokoro ONNX - try voice name first, then fallback to index
            try:
                audio_data, sample_rate = self._pipeline.create(text, voice=self._voice, speed=self._speed)
            except:
                # Fallback to voice index 0
                logger.debug(f"Voice name '{self._voice}' failed, trying index 0")
                audio_data, sample_rate = self._pipeline.create(text, voice=0, speed=self._speed)
            
            generation_time = time.time() - start_time
            logger.debug(f"Generated {len(text)} chars in {generation_time:.3f}s ({len(text)/generation_time:.1f} chars/s)")
            
            return audio_data, sample_rate
            
        except Exception as e:
            logger.error(f"Kokoro TTS generation failed: {e}")
            return None
    
    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """Generate speech from text using native Kokoro ONNX"""
        
        if not text.strip():
            return
            
        logger.debug(f"Generating TTS for: '{text[:50]}{'...' if len(text) > 50 else ''}'")
        
        # Emit TTS start event
        if self._event_emitter:
            await self._event_emitter.emit("tts_audio_start", {
                "text": text,
                "voice": self._voice,
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
                            "voice": self._voice,
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