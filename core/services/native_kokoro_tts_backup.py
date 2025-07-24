# core/services/native_kokoro_tts.py
"""Native Kokoro ONNX TTS Service for Apple Silicon with Metal acceleration"""
import asyncio
import time
import numpy as np
from typing import AsyncGenerator, Optional
import logging
from concurrent.futures import ThreadPoolExecutor

from pipecat.frames.frames import Frame, TTSAudioRawFrame, TTSStartedFrame, TTSStoppedFrame
from pipecat.services.tts_service import TTSService

logger = logging.getLogger(__name__)


class NativeKokoroTTSService(TTSService):
    """
    Native Kokoro ONNX TTS service optimized for Apple Silicon
    Uses kokoro-onnx for Metal acceleration and sub-second generation
    """
    
    def __init__(
        self,
        *,
        voice: str = "af_heart",
        speed: float = 1.0,
        sample_rate: int = 24000,
        **kwargs
    ):
        super().__init__(
            aggregate_sentences=False,  # Stream immediately for ultra-low latency
            **kwargs
        )
        
        self._voice = voice
        self._speed = speed
        self._sample_rate = sample_rate
        
        # Thread pool for non-blocking TTS generation
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kokoro-tts")
        
        # Initialize Kokoro ONNX pipeline
        self._pipeline = None
        self._initialize_pipeline()
        
    def _download_models_if_needed(self):
        """Download Kokoro models if they don't exist"""
        from pathlib import Path
        
        cache_dir = Path.home() / ".cache" / "kokoro"
        model_path = cache_dir / "kokoro-v1.0.onnx"
        voices_path = cache_dir / "voices-v1.0.bin"
        
        # Check if model and voices files exist and are properly sized
        model_exists = model_path.exists() and model_path.stat().st_size > 300_000_000  # >300MB
        voices_exists = voices_path.exists() and voices_path.stat().st_size > 25_000_000  # >25MB
        
        if model_exists and voices_exists:
            return str(model_path), str(voices_path)
        
        # Download models
        logger.info("📥 Downloading Kokoro models (first time only)...")
        
        try:
            from huggingface_hub import hf_hub_download
            
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            if not model_exists:
                logger.info("Downloading model.onnx (82MB)...")
                model_path = hf_hub_download(
                    repo_id="onnx-community/Kokoro-82M-ONNX",
                    filename="onnx/model.onnx",
                    cache_dir=str(cache_dir),
                    local_dir=str(cache_dir)
                )
            
            if not voices_exists:
                logger.info("Downloading voice files (11 voices, ~6MB total)...")
                voices_dir.mkdir(parents=True, exist_ok=True)
                # Download all voice files
                voice_files = [
                    "af.bin", "af_bella.bin", "af_nicole.bin", "af_sarah.bin", "af_sky.bin",
                    "am_adam.bin", "am_michael.bin", "bf_emma.bin", "bf_isabella.bin", 
                    "bm_george.bin", "bm_lewis.bin"
                ]
                for voice_file in voice_files:
                    hf_hub_download(
                        repo_id="onnx-community/Kokoro-82M-ONNX",
                        filename=f"voices/{voice_file}",
                        cache_dir=str(cache_dir),
                        local_dir=str(cache_dir)
                    )
            
            return str(model_path), str(voices_dir)
            
        except ImportError:
            logger.error("huggingface-hub not installed. Install with: pip install huggingface-hub")
            raise
        except Exception as e:
            logger.error(f"Model download failed: {e}")
            logger.error("Manual download: https://huggingface.co/onnx-community/Kokoro-82M-ONNX")
            raise

    def _initialize_pipeline(self):
        """Initialize the Kokoro ONNX pipeline with Metal optimization"""
        try:
            import kokoro_onnx
            from kokoro_onnx import Kokoro
            
            logger.info(f"🚀 Initializing native Kokoro ONNX TTS with voice: {self._voice}")
            
            # Download models if needed
            model_path, voices_dir = self._download_models_if_needed()
            
            logger.info(f"Using model: {model_path}")
            logger.info(f"Using voices dir: {voices_dir}")
            
            # Load all voice files and create a voices array
            import numpy as np
            import tempfile
            from pathlib import Path
            
            voice_files = [
                "af.bin", "af_bella.bin", "af_nicole.bin", "af_sarah.bin", "af_sky.bin",
                "am_adam.bin", "am_michael.bin", "bf_emma.bin", "bf_isabella.bin", 
                "bm_george.bin", "bm_lewis.bin"
            ]
            
            # Load all voices into a single array and create mapping
            voices_list = []
            voice_mapping = {}
            for i, voice_file in enumerate(voice_files):
                voice_path = Path(voices_dir) / voice_file
                if voice_path.exists():
                    voice_data = np.fromfile(voice_path, dtype=np.float32)
                    voices_list.append(voice_data)
                    voice_mapping[voice_file.replace('.bin', '')] = i
                    logger.debug(f"Loaded voice: {voice_file} with shape {voice_data.shape}")
            
            if not voices_list:
                raise FileNotFoundError(f"No voice files found in {voices_dir}")
            
            # Store voice mapping for reference
            self._voice_mapping = voice_mapping
            logger.debug(f"Voice mapping: {self._voice_mapping}")
            
            # Create voices matrix for kokoro-onnx compatibility
            # The ONNX model expects style input of shape [1, 256], so we need to truncate/transform the voice embeddings
            original_embedding_size = voices_list[0].shape[0]  # 131072
            model_style_size = 256  # Expected by ONNX model
            max_tokens = 512  # Maximum tokens the model can handle
            
            # Find the requested voice or default to af_bella
            voice_index = self._voice_mapping.get(self._voice, 1)  # Default to af_bella
            selected_voice = voices_list[voice_index]
            logger.info(f"Selected voice: {self._voice} (index {voice_index})")
            
            # Transform voice embedding to match model expectations
            # Option 1: Take first 256 elements (preserves more voice characteristics)
            # Option 2: Average reshape (131072 -> 256) - can destroy voice quality
            # Let's try option 1: take first 256 elements to preserve voice characteristics
            reshaped_voice = selected_voice[:model_style_size]
            logger.info(f"Transformed voice from {original_embedding_size} to {model_style_size} dimensions (first 256 elements)")
            
            # Create voice matrix where each row is a 2D voice embedding (1, 256)
            # When kokoro does voice[len(tokens)], it should return a (1, 256) array
            voices_list_2d = []
            for i in range(max_tokens):
                voices_list_2d.append(reshaped_voice.reshape(1, -1))  # Shape: (1, 256)
            
            voices_array = np.array(voices_list_2d)  # Shape: (max_tokens, 1, 256)
            logger.info(f"Created voices matrix with shape: {voices_array.shape} for token-based indexing")
            
            # Save voices array to temporary file
            with tempfile.NamedTemporaryFile(suffix='.npy', delete=False) as tmp_file:
                np.save(tmp_file.name, voices_array)
                voices_path = tmp_file.name
            
            self._pipeline = Kokoro(
                model_path=model_path,
                voices_path=voices_path,
                espeak_config=None  # Use default
            )
            
            # Warm up the pipeline with a test generation - voices are now properly loaded
            test_audio, test_sr = self._pipeline.create("Hello", voice=self._pipeline.voices, speed=self._speed)
            logger.debug(f"Warmup complete - generated {len(test_audio)} samples at {test_sr}Hz")
            
            logger.info("✅ Native Kokoro ONNX TTS initialized and warmed up")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Kokoro ONNX: {e}")
            self._pipeline = None
            raise
    
    def _load_voice(self, voice_name: str) -> np.ndarray:
        """Load voice data from an individual voice file"""
        from pathlib import Path
        
        voice_file = Path(self._voices_dir) / f"{voice_name}.bin"
        if not voice_file.exists():
            logger.warning(f"Voice file not found: {voice_file}. Available voices:")
            available_voices = [f.stem for f in Path(self._voices_dir).glob("*.bin")]
            for v in available_voices:
                logger.warning(f"  - {v}")
            # Fallback to first available voice
            if available_voices:
                voice_name = available_voices[0]
                voice_file = Path(self._voices_dir) / f"{voice_name}.bin"
                logger.warning(f"Using fallback voice: {voice_name}")
            else:
                raise FileNotFoundError(f"No voice files found in {self._voices_dir}")
        
        # Load voice data as float32 array and reshape to 2D (1, embedding_size)
        voice_data = np.fromfile(voice_file, dtype=np.float32)
        voice_data = voice_data.reshape(1, -1)  # Reshape to (1, embedding_size)
        logger.debug(f"Loaded voice '{voice_name}' with shape: {voice_data.shape}")
        return voice_data
    
    def _generate_audio_sync(self, text: str) -> Optional[tuple[np.ndarray, int]]:
        """Synchronous audio generation - runs in thread pool"""
        if not self._pipeline:
            logger.error("Kokoro pipeline not initialized")
            return None
            
        try:
            start_time = time.time()
            
            # Generate audio using Kokoro ONNX with the pre-loaded voices matrix
            audio_data, sample_rate = self._pipeline.create(text, voice=self._pipeline.voices, speed=self._speed)
            
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
            from pipecat.frames.frames import EndFrame
            await super().stop(EndFrame())