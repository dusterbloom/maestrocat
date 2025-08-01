# core/services/mlx_whisper_optimized_stt.py
"""Optimized MLX Whisper STT Service with Enhanced Performance for MaestroCat"""

import asyncio
import logging
import time
import numpy as np
from typing import Optional, AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

from pipecat.frames.frames import Frame, TranscriptionFrame, ErrorFrame
from pipecat.services.whisper.stt import WhisperSTTServiceMLX, MLXModel
from pipecat.transcriptions.language import Language

logger = logging.getLogger(__name__)


class OptimizedMLXWhisperSTTService(WhisperSTTServiceMLX):
    """
    High-performance MLX Whisper STT with optimizations for sub-100ms latency.
    
    Key optimizations:
    - Reduced audio buffer threshold (300ms instead of 1s)
    - Concurrent processing with thread pool
    - Optimized chunk processing
    - Smart VAD integration
    - Efficient memory management
    """
    
    def __init__(
        self,
        *,
        model: MLXModel = MLXModel.LARGE_V3_TURBO_Q4,  # Fastest quantized model
        language: Optional[Language] = Language.EN,
        no_speech_prob: float = 0.4,  # Lower threshold for faster detection
        min_audio_duration: float = 0.3,  # Process after 300ms instead of 1s
        chunk_length: int = 30,  # Process in 30s chunks
        use_vad: bool = True,  # Use VAD to skip silence
        vad_threshold: float = 0.5,
        max_workers: int = 2,  # Concurrent processing threads
        **kwargs
    ):
        super().__init__(
            model=model,
            language=language,
            no_speech_prob=no_speech_prob,
            **kwargs
        )
        
        # Optimization parameters
        self._min_audio_duration = min_audio_duration
        self._chunk_length = chunk_length
        self._use_vad = use_vad
        self._vad_threshold = vad_threshold
        
        # Performance tracking
        self._model_preloaded = False
        self._last_process_time = 0
        self._total_latency_ms = 0
        self._process_count = 0
        
        # Audio buffer management
        self._audio_buffer = bytearray()
        self._sample_rate = 16000
        self._min_samples = int(self._sample_rate * self._min_audio_duration)
        
        # Thread pool for concurrent processing
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._processing = False
        
        # Warmup audio for model initialization
        self._warmup_audio = None
        
        logger.info(f"🚀 Optimized MLX Whisper STT initialized")
        logger.info(f"📊 Model: {model}, Min audio: {min_audio_duration}s")
        logger.info(f"⚡ VAD: {use_vad}, Threshold: {vad_threshold}")
    
    async def _preload_model(self):
        """
        Enhanced preloading with warmup for instant transcription.
        """
        if self._model_preloaded:
            logger.info("✅ MLX Whisper model already preloaded")
            return
        
        try:
            logger.info(f"🚀 Preloading and warming up MLX Whisper model...")
            start_time = time.time()
            
            # Import MLX modules
            import mlx_whisper
            from huggingface_hub import snapshot_download
            
            # Model paths for different variants
            model_paths = {
                MLXModel.TINY: "mlx-community/whisper-tiny-mlx-q4",
                MLXModel.MEDIUM: "mlx-community/whisper-medium-mlx-q4",
                MLXModel.LARGE_V3: "mlx-community/whisper-large-v3-mlx",
                MLXModel.LARGE_V3_TURBO: "mlx-community/whisper-large-v3-turbo",
                MLXModel.LARGE_V3_TURBO_Q4: "mlx-community/whisper-large-v3-turbo-mlx-q4",
                MLXModel.DISTIL_LARGE_V3: "mlx-community/distil-whisper-large-v3",
            }
            
            model_path = model_paths.get(self._model, "mlx-community/whisper-large-v3-turbo-mlx-q4")
            
            # Download model files
            logger.info(f"📥 Ensuring model {model_path} is downloaded...")
            loop = asyncio.get_event_loop()
            
            def _download_model():
                try:
                    snapshot_download(
                        repo_id=model_path, 
                        allow_patterns=["*.safetensors", "*.json", "*.npz"]
                    )
                    return True
                except Exception as e:
                    logger.error(f"Model download failed: {e}")
                    return False
            
            success = await loop.run_in_executor(None, _download_model)
            
            if success:
                # Create warmup audio (0.5s of silence)
                self._warmup_audio = np.zeros(int(self._sample_rate * 0.5), dtype=np.float32)
                
                # Perform warmup transcription
                logger.info("🔥 Warming up model with dummy transcription...")
                warmup_start = time.time()
                
                # This triggers the actual model loading
                await self._transcribe_audio_chunk(self._warmup_audio)
                
                warmup_time = (time.time() - warmup_start) * 1000
                logger.info(f"✅ Warmup completed in {warmup_time:.1f}ms")
                
                self._model_preloaded = True
                total_time = time.time() - start_time
                logger.info(f"✅ Model preloaded and warmed up in {total_time:.2f}s")
            else:
                logger.warning("⚠️ Model download failed, will retry on first use")
                
        except Exception as e:
            logger.error(f"❌ Preload failed: {e}")
            logger.warning("⚠️ Continuing without preload - model will load on first use")
    
    async def process_frame(self, frame: Frame, direction):
        """Process incoming audio frames with optimized buffering."""
        await super().process_frame(frame, direction)
        
        # Handle audio frames
        if hasattr(frame, 'audio') and frame.audio is not None:
            # Add to buffer
            self._audio_buffer.extend(frame.audio)
            
            # Process when we have minimum audio (300ms by default)
            if len(self._audio_buffer) >= self._min_samples * 2:  # 16-bit audio
                if not self._processing:
                    asyncio.create_task(self._process_audio_buffer())
        
        # Pass frame downstream
        await self.push_frame(frame, direction)
    
    async def _process_audio_buffer(self):
        """Process audio buffer with optimizations."""
        if self._processing or len(self._audio_buffer) < self._min_samples * 2:
            return
        
        self._processing = True
        
        try:
            # Extract audio data
            audio_data = np.frombuffer(bytes(self._audio_buffer), dtype=np.int16)
            audio_float = audio_data.astype(np.float32) / 32768.0
            
            # Clear buffer immediately to avoid blocking new audio
            self._audio_buffer.clear()
            
            # Apply VAD if enabled
            if self._use_vad and self._is_silence(audio_float):
                logger.debug("VAD: Skipping silent audio")
                return
            
            # Start timing
            start_time = time.time()
            
            # Transcribe audio
            result = await self._transcribe_audio_chunk(audio_float)
            
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000
            self._total_latency_ms += latency_ms
            self._process_count += 1
            avg_latency = self._total_latency_ms / self._process_count
            
            # Process result
            if result and "text" in result:
                text = result["text"].strip()
                
                if text and text not in ["[BLANK_AUDIO]", ""]:
                    logger.info(f"📝 Transcription: '{text}' (latency: {latency_ms:.1f}ms, avg: {avg_latency:.1f}ms)")
                    
                    # Create transcription frame
                    frame = TranscriptionFrame(
                        text=text,
                        user_id="user",
                        timestamp=time.time()
                    )
                    
                    await self.push_frame(frame)
                    
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            await self.push_frame(ErrorFrame(f"STT error: {str(e)}"))
        finally:
            self._processing = False
    
    async def _transcribe_audio_chunk(self, audio: np.ndarray) -> dict:
        """Transcribe audio chunk with MLX Whisper."""
        loop = asyncio.get_event_loop()
        
        def _transcribe():
            try:
                import mlx_whisper
                
                # Handle language parameter
                language_str = None
                if self._language:
                    if hasattr(self._language, 'value'):
                        language_str = self._language.value
                    else:
                        language_str = str(self._language)
                
                # Get model path
                model_paths = {
                    MLXModel.TINY: "mlx-community/whisper-tiny-mlx-q4",
                    MLXModel.MEDIUM: "mlx-community/whisper-medium-mlx-q4",
                    MLXModel.LARGE_V3: "mlx-community/whisper-large-v3-mlx",
                    MLXModel.LARGE_V3_TURBO: "mlx-community/whisper-large-v3-turbo",
                    MLXModel.LARGE_V3_TURBO_Q4: "mlx-community/whisper-large-v3-turbo-mlx-q4",
                    MLXModel.DISTIL_LARGE_V3: "mlx-community/distil-whisper-large-v3",
                }
                
                model_path = model_paths.get(self._model, "mlx-community/whisper-large-v3-turbo-mlx-q4")
                
                # Transcribe with optimized settings
                result = mlx_whisper.transcribe(
                    audio,
                    path_or_hf_repo=model_path,
                    language=language_str,
                    fp16=True,  # Use FP16 for faster processing
                    verbose=False,
                    condition_on_previous_text=False,  # Faster without conditioning
                    compression_ratio_threshold=2.4,
                    logprob_threshold=-1.0,
                    no_speech_threshold=self._no_speech_prob,
                    chunk_length=self._chunk_length,
                )
                
                return result
                
            except Exception as e:
                logger.error(f"MLX transcription error: {e}")
                return None
        
        # Run in thread pool to avoid blocking
        return await loop.run_in_executor(self._executor, _transcribe)
    
    def _is_silence(self, audio: np.ndarray) -> bool:
        """Simple VAD to detect silence."""
        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio**2))
        
        # Convert to dB
        if rms > 0:
            db = 20 * np.log10(rms)
            # Typical silence is below -40dB
            return db < -40
        
        return True
    
    async def stop(self):
        """Clean up resources."""
        await super().stop()
        
        # Shutdown thread pool
        self._executor.shutdown(wait=False)
        
        # Clear buffers
        self._audio_buffer.clear()
        self._warmup_audio = None
        
        logger.info(f"📊 Final STT stats - Avg latency: {self._total_latency_ms / max(1, self._process_count):.1f}ms over {self._process_count} transcriptions")
    
    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Required by STTService base class."""
        # This is handled in process_frame instead
        yield