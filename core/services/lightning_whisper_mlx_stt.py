# core/services/lightning_whisper_mlx_stt.py
"""Lightning Whisper MLX STT Service for Pipecat - Optimized for Apple M4 Silicon"""
import asyncio
import time
import numpy as np
from typing import AsyncGenerator, Optional, Dict, Any
import logging
from pathlib import Path

try:
    import lightning_whisper_mlx
    LIGHTNING_MLX_AVAILABLE = True
except ImportError:
    LIGHTNING_MLX_AVAILABLE = False
    lightning_whisper_mlx = None

try:
    import mlx_whisper
    MLX_WHISPER_AVAILABLE = True
except ImportError:
    MLX_WHISPER_AVAILABLE = False
    mlx_whisper = None

try:
    from huggingface_hub import snapshot_download
    HF_HUB_AVAILABLE = True
except ImportError:
    HF_HUB_AVAILABLE = False

from pipecat.frames.frames import Frame, TranscriptionFrame, ErrorFrame
from pipecat.services.stt_service import STTService
from pipecat.transcriptions.language import Language

logger = logging.getLogger(__name__)


class LightningWhisperMLXService(STTService):
    """
    Lightning-fast Whisper MLX integration for Pipecat
    Optimized for Apple M4 Silicon with:
    - Metal/MPS GPU acceleration
    - Quantized model support
    - Batch processing capabilities
    - 5-10x faster than whisper.cpp
    """
    
    def __init__(
        self,
        *,
        model: str = "distil-large-v3",
        language: Optional[Language] = Language.EN,
        temperature: float = 0.0,
        compute_type: str = "float16",  # float16, int8, or int4
        batch_size: int = 1,
        beam_size: int = 1,
        vad_filter: bool = True,
        vad_threshold: float = 0.5,
        event_emitter = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        if not LIGHTNING_MLX_AVAILABLE and not MLX_WHISPER_AVAILABLE:
            raise ImportError(
                "Neither lightning-whisper-mlx nor mlx-whisper available. Install with: pip install lightning-whisper-mlx"
            )
        
        self._model_name = model
        self._language = language
        self._temperature = temperature
        self._compute_type = compute_type
        self._batch_size = batch_size
        self._beam_size = beam_size
        self._vad_filter = vad_filter
        self._vad_threshold = vad_threshold
        self._event_emitter = event_emitter
        
        # Model instance and backend selection
        self._model = None
        self._processor = None
        self._backend = None  # 'lightning', 'mlx', or None
        
        # Performance tracking
        self._last_stt_latency = 0.0
        
        # Audio buffer
        self._audio_buffer = bytearray()
        self._sample_rate = 16000
        self._frame_duration = 30  # ms
        self._frame_samples = int(self._sample_rate * self._frame_duration / 1000)
        
        # Determine best available backend
        if LIGHTNING_MLX_AVAILABLE:
            self._backend = 'lightning'
            logger.info(f"🚀 Using Lightning Whisper MLX (5-10x faster) with model: {model}")
        elif MLX_WHISPER_AVAILABLE:
            self._backend = 'mlx'
            logger.info(f"⚡ Using MLX Whisper (fallback) with model: {model}")
        else:
            raise ImportError("No MLX backend available")
            
        logger.info(f"Compute type: {compute_type}, Batch size: {batch_size}")
        
    async def _preload_model(self):
        """Public method for agent to preload the model"""
        logger.info("🚀 Pre-loading Lightning Whisper MLX model...")
        await self._load_model()
        logger.info("✅ Lightning Whisper MLX model pre-loaded and ready")
        
    async def start(self, frame: Frame):
        """Start the STT service and load model"""
        await super().start(frame)
        
        # Load model asynchronously (skip if already loaded by preload)
        if self._model is None:
            await self._load_model()
        
    async def _load_model(self):
        """Load the MLX Whisper model"""
        # Skip if already loaded
        if self._model is not None:
            logger.info(f"✅ {self._backend} Whisper model already loaded")
            return
            
        try:
            logger.info(f"Loading {self._backend} Whisper model: {self._model_name}")
            start_time = time.time()
            
            if self._backend == 'lightning':
                # Lightning Whisper MLX - fastest option
                model_key = self._get_lightning_model_path()
                
                # Check if model key is valid
                await self._ensure_model_available(model_key)
                
                self._model = lightning_whisper_mlx.LightningWhisperMLX(
                    model=model_key,
                    batch_size=self._batch_size,
                    quant=self._get_lightning_quant()
                )
            elif self._backend == 'mlx':
                # Standard MLX Whisper fallback
                model_path = self._get_model_path()
                await self._ensure_mlx_model_available(model_path)
                self._model = None  # MLX Whisper uses transcribe function directly
            
            load_time = time.time() - start_time
            logger.info(f"✅ Model loaded in {load_time:.2f} seconds")
            
            # Warm up the model
            await self._warmup_model()
            
        except Exception as e:
            logger.error(f"Failed to load {self._backend} Whisper model: {e}")
            raise
    
    def _get_lightning_model_path(self) -> str:
        """Get model key for Lightning Whisper MLX"""
        # Lightning Whisper MLX uses specific model keys, not HuggingFace paths
        lightning_model_mapping = {
            "tiny": "tiny",
            "base": "base", 
            "small": "small",
            "medium": "medium",
            "large": "large-v3",  # Use latest version
            "large-v3": "large-v3",
            "large-v2": "large-v2",
            "distil-large-v3": "distil-large-v3",
            "distil-large-v2": "distil-large-v2",
            "distil-medium": "distil-medium.en",
            "distil-small": "distil-small.en"
        }
        
        model_key = lightning_model_mapping.get(self._model_name, self._model_name)
        logger.info(f"Using Lightning Whisper MLX model key: {model_key}")
        return model_key
    
    def _get_lightning_quant(self) -> str:
        """Get quantization type for Lightning Whisper MLX"""
        # Map compute_type to Lightning MLX quantization
        quant_mapping = {
            "float16": None,  # No quantization
            "int8": "8bit",
            "int4": "4bit"
        }
        
        return quant_mapping.get(self._compute_type, None)
    
    def _get_model_path(self) -> str:
        """Get model path for standard MLX Whisper (fallback)"""
        # Standard MLX Whisper model mapping
        model_mapping = {
            "tiny": "mlx-community/whisper-tiny-mlx-q4",
            "base": "mlx-community/whisper-base-mlx-q4", 
            "small": "mlx-community/whisper-small-mlx-q4",
            "medium": "mlx-community/whisper-medium-mlx-q4",
            "large": "mlx-community/whisper-large-v3-mlx",
            "large-v3": "mlx-community/whisper-large-v3-mlx",
            "distil-large-v3": "mlx-community/distil-large-v3",
            "distil-medium": "mlx-community/distil-whisper-medium.en"
        }
        
        return model_mapping.get(self._model_name, self._model_name)
    
    async def _ensure_model_available(self, model_key: str):
        """Ensure Lightning Whisper MLX model is available"""
        try:
            logger.info(f"Model {model_key} will be auto-downloaded by Lightning Whisper MLX if needed")
            
            # Lightning Whisper MLX handles model downloads automatically
            # We just need to verify the model key is valid
            import lightning_whisper_mlx.lightning as lightning
            
            if model_key not in lightning.models:
                available_models = list(lightning.models.keys())
                raise ValueError(f"Invalid model key '{model_key}'. Available models: {available_models}")
            
            logger.info(f"✅ Model key '{model_key}' is valid")
                
        except Exception as e:
            logger.error(f"Model validation failed: {e}")
            raise
    
    async def _ensure_mlx_model_available(self, model_path: str):
        """Ensure MLX Whisper model is available"""
        try:
            logger.info(f"Checking MLX model availability: {model_path}")
            
            # MLX models are handled by the mlx_whisper.load_models function
            loop = asyncio.get_event_loop()
            
            def _check_mlx_model():
                try:
                    # This will download the model if it doesn't exist
                    mlx_whisper.load_models.load_model(model_path)
                    return True
                except Exception as e:
                    logger.warning(f"MLX model check failed: {e}")
                    return False
            
            success = await loop.run_in_executor(None, _check_mlx_model)
            if success:
                logger.info(f"✅ MLX model {model_path} is available")
            else:
                logger.warning(f"⚠️ MLX model {model_path} may not be available")
                
        except Exception as e:
            logger.warning(f"MLX model availability check failed: {e}")
    
    def _get_dtype(self):
        """Get the appropriate dtype for compute type"""
        import mlx.core as mx
        
        dtype_mapping = {
            "float16": mx.float16,
            "float32": mx.float32,
            "int8": mx.int8,
            "int4": mx.int4  # Extreme quantization for max speed
        }
        
        return dtype_mapping.get(self._compute_type, mx.float16)
    
    async def _warmup_model(self):
        """Warm up the model with a dummy transcription"""
        try:
            logger.info(f"Warming up {self._backend} Whisper...")
            
            # Create a short silent audio sample
            dummy_audio = np.zeros(self._sample_rate, dtype=np.float32)
            
            # Run inference only if we have a model instance (Lightning) or for MLX
            if self._backend == 'lightning' and self._model:
                try:
                    start_time = time.time()
                    result = await self._transcribe_audio(dummy_audio)
                    warmup_time = (time.time() - start_time) * 1000
                    logger.info(f"✅ Model warmed up in {warmup_time:.1f}ms")
                except Exception as e:
                    logger.warning(f"Lightning warmup failed (non-critical): {e}")
            elif self._backend == 'mlx':
                logger.info("✅ MLX Whisper ready (no warmup needed)")
            
        except Exception as e:
            logger.warning(f"Warmup failed (non-critical): {e}")
    
    async def _transcribe_audio(self, audio: np.ndarray) -> Dict[str, Any]:
        """Transcribe audio using the selected backend"""
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        
        def _transcribe():
            # Handle language parameter - could be Language enum or string
            language_str = None
            if self._language:
                if hasattr(self._language, 'value'):
                    language_str = self._language.value
                else:
                    language_str = str(self._language)
            
            if self._backend == 'lightning' and self._model:
                # Lightning Whisper MLX - simpler API, no temperature support
                return self._model.transcribe(
                    audio,
                    language=language_str
                )
            elif self._backend == 'mlx':
                # Standard MLX Whisper
                return mlx_whisper.transcribe(
                    audio,
                    path_or_hf_repo=self._get_model_path(),
                    language=language_str,
                    temperature=self._temperature
                )
            else:
                raise RuntimeError(f"Unknown backend: {self._backend}")
        
        return await loop.run_in_executor(None, _transcribe)
    
    async def process_frame(self, frame: Frame, direction):
        """Process incoming frames"""
        await super().process_frame(frame, direction)
        
        # Handle audio frames
        if hasattr(frame, 'audio') and frame.audio is not None:
            # Add to buffer
            self._audio_buffer.extend(frame.audio)
            
            # Process when we have enough audio (e.g., 1 second)
            min_samples = self._sample_rate * 2  # 1 second in bytes (16-bit audio)
            
            if len(self._audio_buffer) >= min_samples:
                await self._process_audio_buffer()
        
        # Pass frame downstream
        await self.push_frame(frame, direction)
    
    async def _process_audio_buffer(self):
        """Process accumulated audio buffer"""
        if not self._model or len(self._audio_buffer) < self._sample_rate:
            return
        
        try:
            # Convert buffer to numpy array
            audio_data = np.frombuffer(bytes(self._audio_buffer), dtype=np.int16)
            audio_float = audio_data.astype(np.float32) / 32768.0
            
            # Clear buffer
            self._audio_buffer.clear()
            
            # Start timing
            start_time = time.time()
            
            # Transcribe with Lightning MLX
            result = await self._transcribe_audio(audio_float)
            
            # Calculate latency
            self._last_stt_latency = (time.time() - start_time) * 1000
            
            # Process result
            if result and "text" in result:
                text = result["text"].strip()
                
                if text and text not in ["[BLANK_AUDIO]", ""]:
                    logger.info(f"Transcription: '{text}' (latency: {self._last_stt_latency:.1f}ms)")
                    
                    # Emit transcription event
                    if self._event_emitter:
                        await self._event_emitter.emit("transcription_final", {
                            "text": text,
                            "confidence": 1.0,
                            "timestamp": time.time(),
                            "user_id": "user"
                        })
                        
                        # Emit metrics
                        await self._event_emitter.emit("metrics_update", {
                            "stt_latency_ms": self._last_stt_latency,
                            "llm_latency_ms": 0.0,
                            "tts_latency_ms": 0.0,
                            "total_latency_ms": self._last_stt_latency,
                            "timestamp": time.time(),
                            "component": "stt"
                        })
                    
                    # Create transcription frame
                    frame = TranscriptionFrame(
                        text=text,
                        user_id="user",
                        timestamp=time.time()
                    )
                    
                    await self.push_frame(frame)
                    
        except Exception as e:
            logger.error(f"Lightning MLX transcription error: {e}")
            await self.push_frame(ErrorFrame(f"STT error: {str(e)}"))
    
    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Required by STTService base class"""
        # This is handled in process_frame instead
        yield
    
    async def stop(self):
        """Stop the STT service"""
        await super().stop()
        
        # Clear model from memory
        self._model = None
        logger.info("Lightning Whisper MLX stopped")