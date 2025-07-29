"""
macOS Native Platform Strategy

Implements platform strategy for macOS native services including:
- WhisperCpp STT (native C++ implementation, fastest)
- Native Ollama LLM 
- macOS System TTS or PyTTSx3
- Native Kokoro ONNX TTS (optional)
- Apple Silicon optimizations (Metal)
"""

import asyncio
import logging
import subprocess
from typing import Any, Dict, List, Tuple

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.transports.network.fastapi_websocket import FastAPIWebsocketParams
from ..services.whispercpp_stt import WhisperCppSTTService
from ..services.whispercpp_streaming_stt import WhisperCppStreamingSTTService

from .strategy import PlatformStrategy, PlatformType, PlatformInfo, PlatformCapabilities, ServiceSpecs
from ..services.ollama_llm import OLLamaLLMService
from ..services.macos_tts import MacOSTTSService, MacOSPyTTSx3Service
from ..serializers import RawAudioSerializer

logger = logging.getLogger(__name__)


class MacOSPlatformStrategy(PlatformStrategy):
    """
    Platform strategy for macOS native services.
    
    Handles:
    - Apple Silicon optimizations (Metal, native performance)
    - Native service lifecycle management  
    - Fallback service selection
    - Performance tuning for macOS
    """
    
    def __init__(self, config: Any):
        super().__init__(config)
        self._mlx_available = None
        self._native_services = None
    
    @property
    def platform_info(self) -> PlatformInfo:
        """Get macOS platform information"""
        # Lazy load capabilities
        if self._mlx_available is None:
            self._mlx_available = self._check_mlx_availability()
        if self._native_services is None:
            self._native_services = self._check_native_services()
        
        capabilities = PlatformCapabilities(
            has_gpu=False,  # macOS doesn't use NVIDIA GPUs for our services
            supports_metal=True,  # macOS always has Metal
            supports_mlx=self._mlx_available,
            docker_available=False,  # Not used in native strategy
            native_services=self._native_services
        )
        
        description = "macOS native services"
        if self._mlx_available:
            description += " (Apple Silicon with native acceleration)"
        else:
            description += " (Intel/fallback)"
        
        # Recommend models based on Apple Silicon capabilities
        # WhisperCpp native performance is excellent across all Apple Silicon
        if self._mlx_available:  # Apple Silicon detected
            recommended_models = {
                "stt": "distil-large-v3",  # WhisperCpp native is fast enough for base model
                "llm": "llama3.2:3b",  # Good balance for Apple Silicon
                "tts": "af_bella"
            }
        else:  # Intel Mac
            recommended_models = {
                "stt": "base",  # Conservative for Intel Macs
                "llm": "llama3.2:1b",  # Smaller model for older hardware
                "tts": "Samantha"  # macOS system voice
            }
        
        return PlatformInfo(
            platform_type=PlatformType.MACOS_NATIVE,
            capabilities=capabilities,
            description=description,
            recommended_models=recommended_models
        )
    
    @property
    def service_specs(self) -> ServiceSpecs:
        """Get service specifications for macOS platform"""
        # Determine TTS service based on config
        tts_service = getattr(self.config.tts, 'service', 'macos')
        if tts_service == 'native_kokoro':
            tts_class = "NativeKokoroTTSService"
        elif tts_service == 'pyttsx3':
            tts_class = "MacOSPyTTSx3Service"
        else:
            tts_class = "MacOSTTSService"
        
        # Determine STT service based on config
        stt_service = getattr(self.config.stt, 'service', 'whispercpp')
        if stt_service == 'lightning_whisper_mlx':
            stt_class = "LightningWhisperMLXService"
        elif stt_service == 'mlx_whisper':
            stt_class = "WhisperCppSTTService"  # Use WhisperCpp as implementation for now
        else:
            stt_class = "WhisperCppSTTService"
        
        return ServiceSpecs(
            stt_service=stt_class,
            llm_service="OLLamaLLMService",
            tts_service=tts_class,
            transport_class="FastAPIWebsocketTransport",
            additional_processors=["EventEmitter", "TranscriptionEventProcessor"]
        )
    
    def _check_mlx_availability(self) -> bool:
        """Check if MLX is available for compatibility (legacy)"""
        try:
            import mlx
            return True
        except ImportError:
            return False
    
    def _check_native_services(self) -> List[str]:
        """Check available native macOS services"""
        services = []
        
        # Check Ollama
        try:
            result = subprocess.run(
                ["ollama", "--version"], 
                capture_output=True, 
                check=True,
                timeout=5
            )
            services.append("ollama")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Check macOS say command
        try:
            result = subprocess.run(
                ["which", "say"], 
                capture_output=True, 
                check=True,
                timeout=5
            )
            services.append("macos-tts")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Check FFmpeg
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], 
                capture_output=True, 
                check=True,
                timeout=5
            )
            services.append("ffmpeg")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        return services
    
    async def check_dependencies(self) -> Tuple[bool, List[str]]:
        """Check macOS native dependencies"""
        missing = []
        
        # Check Ollama
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:11434/api/version", timeout=2.0)
                if response.status_code != 200:
                    missing.append("Ollama not running (start with: ollama serve)")
        except Exception:
            missing.append("Ollama not available (install with: brew install ollama)")
        
        # Check WhisperCpp for optimal performance
        if "whisper-cpp" not in self._native_services:
            logger.warning("Whisper.cpp not available - install with: brew install whisper-cpp")
            # Not adding to missing since it's optional
        
        # Check macOS say command
        try:
            subprocess.run(["which", "say"], capture_output=True, check=True, timeout=5)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            missing.append("macOS 'say' command not available")
        
        # Check PyTTSx3 if configured
        tts_service = getattr(self.config.tts, 'service', 'macos')
        if tts_service == 'pyttsx3':
            try:
                import pyttsx3
            except ImportError:
                missing.append("PyTTSx3 not available (install with: pip install pyttsx3 pyobjc)")
        
        # Check Native Kokoro if configured
        if tts_service == 'native_kokoro':
            try:
                from ..services.native_kokoro_tts import NativeKokoroTTSService
            except ImportError:
                logger.warning("Native Kokoro not available, will fallback to macOS TTS")
                # Don't add to missing - it's optional with fallback
        
        self._dependencies_checked = True
        return len(missing) == 0, missing
    
    async def setup_services(self) -> bool:
        """Set up native macOS services (mainly check Ollama is running)"""
        logger.info("Checking native macOS services...")
        
        # Check if Ollama is running, start if needed
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:11434/api/version", timeout=5.0)
                if response.status_code == 200:
                    logger.info("✅ Ollama is running")
                    return True
        except Exception:
            pass
        
        # Try to start Ollama
        logger.info("Starting Ollama service...")
        try:
            # Start Ollama in background
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Wait for it to be ready
            for _ in range(30):  # Wait up to 30 seconds
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        response = await client.get("http://localhost:11434/api/version", timeout=2.0)
                        if response.status_code == 200:
                            logger.info("✅ Ollama started successfully")
                            return True
                except Exception:
                    pass
                await asyncio.sleep(1)
            
            logger.warning("⚠️  Ollama may not be ready (timeout)")
            return False
            
        except Exception as e:
            logger.error(f"Failed to start Ollama: {e}")
            return False
    
    async def create_stt_service(self, event_emitter=None):
        """Create STT service based on configuration"""
        stt_config = self.config.stt
        service_type = getattr(stt_config, 'service', 'whispercpp')
        
        model_size = getattr(stt_config, 'model_size', 'small')
        
        # Get language from unified language config
        current_language = getattr(self.config, 'language', 'en')
        language_config = getattr(self.config, 'language_config', {})
        lang_settings = language_config.get(current_language, language_config.get('en', {}))
        language = lang_settings.get('stt_language', 'en')
        
        # Lightning Whisper MLX for M4 optimization (5-10x faster)
        if service_type == 'lightning_whisper_mlx':
            try:
                from ..services.lightning_whisper_mlx_stt import LightningWhisperMLXService
                logger.info(f"🚀 Creating Lightning Whisper MLX with model: {model_size}")
                logger.info("⚡ Using Apple M4 optimized Lightning MLX for 5-10x faster transcription")
                
                return LightningWhisperMLXService(
                    model=model_size,
                    language=language,
                    compute_type=getattr(stt_config, 'compute_type', 'float16'),
                    batch_size=getattr(stt_config, 'batch_size', 1),
                    beam_size=getattr(stt_config, 'beam_size', 1),
                    vad_filter=getattr(stt_config, 'use_vad', True),
                    vad_threshold=getattr(stt_config, 'vad_threshold', 0.5),
                    event_emitter=event_emitter
                )
            except ImportError as e:
                logger.warning(f"Lightning Whisper MLX not available: {e}")
                logger.info("Falling back to WhisperCpp")
                service_type = 'whispercpp'
        
        # Standard MLX Whisper with preloading (2-4x faster than whisper.cpp)
        elif service_type == 'mlx_whisper':
            try:
                from ..services.mlx_whisper_preload_stt import MLXWhisperPreloadSTTService
                from pipecat.services.whisper.stt import MLXModel
                from pipecat.transcriptions.language import Language
                logger.info(f"🚀 Creating preloadable MLX Whisper with model: {model_size}")
                logger.info("⚡ Using MLX Whisper with model preloading for instant first transcription")
                
                # Map model sizes to MLXModel enum (available: TINY, MEDIUM, LARGE_V3, LARGE_V3_TURBO, DISTIL_LARGE_V3, LARGE_V3_TURBO_Q4)
                # Note: Pipecat's MLXModel enum has limited options, so we map to closest available
                model_mapping = {
                    "tiny": MLXModel.TINY,             # Smallest/fastest
                    "base": MLXModel.TINY,             # Map base to tiny (closer to original base size)
                    "small": MLXModel.TINY,            # Map small to tiny (for speed)
                    "medium": MLXModel.MEDIUM,         # Direct mapping
                    "large": MLXModel.LARGE_V3,        # Direct mapping
                    "large-v3": MLXModel.LARGE_V3,     # Direct mapping
                    "large-v3-turbo": MLXModel.LARGE_V3_TURBO,
                    "large-v3-turbo-q4": MLXModel.LARGE_V3_TURBO_Q4,
                    "distil-large-v3": MLXModel.DISTIL_LARGE_V3
                }
                
                model = model_mapping.get(model_size, MLXModel.MEDIUM)
                
                # Always use auto-detect (None) for multilingual support
                # This allows Whisper to detect any language and transcribe it properly
                lang_enum = None
                logger.info("🌍 Using auto-detect mode for multilingual transcription")
                
                return MLXWhisperPreloadSTTService(
                    model=model,
                    language=lang_enum,
                    no_speech_prob=getattr(stt_config, 'no_speech_prob', 0.6)
                )
            except ImportError:
                logger.warning("MLX Whisper not available, falling back to WhisperCpp")
                service_type = 'whispercpp'
        
        # Streaming WhisperCpp (real-time continuous transcription)
        if service_type == 'whispercpp_streaming':
            # Map unsupported models to WhisperCpp equivalents
            whispercpp_model_mapping = {
                "distil-large-v3": "large",  # Use large-v3 as fallback
                "large-v3": "large",
                "distil-medium": "medium",
                "distil-small": "small"
            }
            
            whispercpp_model = whispercpp_model_mapping.get(model_size, model_size)
            logger.info(f"Creating WhisperCpp Streaming STT with model: {whispercpp_model}")
            
            return WhisperCppStreamingSTTService(
                model_size=whispercpp_model,
                language=language,
                translate=getattr(stt_config, 'translate', False),
                sample_rate=getattr(stt_config, 'sample_rate', 16000),
                channels=getattr(stt_config, 'channels', 1),
                block_size=getattr(stt_config, 'block_size', 512),
                max_latency_ms=getattr(stt_config, 'max_latency_ms', 200),
                step_ms=getattr(stt_config, 'step_ms', 1000),
                length_ms=getattr(stt_config, 'length_ms', 5000),
                keep_ms=getattr(stt_config, 'keep_ms', 200),
                voice_threshold=getattr(stt_config, 'voice_threshold', 0.8),
                threads=getattr(stt_config, 'threads', 6),
                event_emitter=event_emitter
            )
        
        # Default: WhisperCpp (still fast, but not as optimized as MLX)
        # Map unsupported models to WhisperCpp equivalents
        whispercpp_model_mapping = {
            "distil-large-v3": "large",  # Use large-v3 as fallback
            "large-v3": "large",
            "distil-medium": "medium",
            "distil-small": "small"
        }
        
        whispercpp_model = whispercpp_model_mapping.get(model_size, model_size)
        logger.info(f"Creating WhisperCpp STT with model: {whispercpp_model}")
        
        return WhisperCppSTTService(
            model_size=whispercpp_model,
            language=language,
            translate=getattr(stt_config, 'translate', False),
            use_vad=getattr(stt_config, 'use_vad', True),
            vad_threshold=getattr(stt_config, 'vad_threshold', 0.5),
            sample_rate=getattr(stt_config, 'sample_rate', 16000),
            event_emitter=event_emitter
        )
    
    async def create_llm_service(self, event_emitter=None):
        """Create native Ollama LLM service"""
        llm_config = self.config.llm
        
        logger.info(f"Creating native Ollama LLM: {llm_config.model}")
        
        return OLLamaLLMService(
            model=llm_config.model,
            base_url=llm_config.base_url,
            temperature=getattr(llm_config, 'temperature', 0.7),
            max_tokens=getattr(llm_config, 'max_tokens', 150),
            top_p=getattr(llm_config, 'top_p', 0.9),
            top_k=getattr(llm_config, 'top_k', 40),
            event_emitter=event_emitter
        )
    
    async def create_tts_service(self, event_emitter=None):
        """Create TTS service based on configuration"""
        tts_config = self.config.tts
        tts_service = getattr(tts_config, 'service', 'macos')
        
        # Get voice from unified language config
        current_language = getattr(self.config, 'language', 'en')
        language_config = getattr(self.config, 'language_config', {})
        lang_settings = language_config.get(current_language, language_config.get('en', {}))
        voice = lang_settings.get('voice', 'af_bella')
        
        if tts_service == 'macos':
            logger.info(f"Creating macOS System TTS with voice: {voice}")
            return MacOSTTSService(
                voice=voice,
                rate=getattr(tts_config, 'rate', 180),
                volume=getattr(tts_config, 'volume', 0.9),
                sample_rate=getattr(tts_config, 'sample_rate', 22050),
                event_emitter=event_emitter
            )
        
        elif tts_service == 'pyttsx3':
            logger.info("Creating PyTTSx3 TTS service")
            return MacOSPyTTSx3Service(
                voice_id=getattr(tts_config, 'voice_id', None),
                rate=getattr(tts_config, 'rate', 200),
                volume=getattr(tts_config, 'volume', 0.8),
                sample_rate=getattr(tts_config, 'sample_rate', 22050),
                event_emitter=event_emitter
            )
        
        elif tts_service == 'native_kokoro':
            logger.info(f"Creating Native Kokoro ONNX TTS with voice: {voice}")
            try:
                from ..services.native_kokoro_tts import NativeKokoroTTSService
                return NativeKokoroTTSService(
                    voice=voice,
                    speed=getattr(tts_config, 'speed', 1.0),
                    sample_rate=getattr(tts_config, 'sample_rate', 24000),
                    event_emitter=event_emitter
                )
            except Exception as e:
                logger.warning(f"Failed to create Native Kokoro, falling back to macOS TTS: {e}")
                return MacOSTTSService(
                    voice="Samantha",
                    rate=180,
                    volume=0.9,
                    sample_rate=22050,
                    event_emitter=event_emitter
                )
        
        else:
            logger.warning(f"Unknown TTS service '{tts_service}', falling back to macOS System TTS")
            return MacOSTTSService(
                voice="Samantha",
                rate=180,
                volume=0.9,
                sample_rate=22050,
                event_emitter=event_emitter
            )
    
    def create_transport_params(self) -> FastAPIWebsocketParams:
        """Create transport parameters optimized for macOS"""
        # Get sample rates from config or use sensible defaults
        audio_in_rate = getattr(self.config.stt, 'sample_rate', 16000)
        audio_out_rate = getattr(self.config.tts, 'sample_rate', 22050)
        
        # Use smaller buffer sizes for lower latency on macOS
        return FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=audio_in_rate,
            audio_out_sample_rate=audio_out_rate,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    confidence=self.config.vad.energy_threshold,
                    start_secs=self.config.vad.min_speech_ms / 1000.0,
                    stop_secs=self.config.vad.pause_ms / 1000.0,
                    min_volume=0.01
                )
            ),
            serializer=RawAudioSerializer()
        )
    
    def get_system_prompt(self) -> str:
        """Get system prompt from unified language config"""
        # Get current language and corresponding system prompt
        current_language = getattr(self.config, 'language', 'en')
        language_config = getattr(self.config, 'language_config', {})
        lang_settings = language_config.get(current_language, language_config.get('en', {}))
        
        return lang_settings.get('system_prompt', 
            "You are MaestroCat, a helpful AI voice assistant. "
            "Keep responses brief and conversational for real-time voice interaction.")
    
    async def apply_platform_optimizations(self) -> Dict[str, Any]:
        """Apply macOS-specific optimizations"""
        optimizations = {}
        
        # MLX optimizations
        if self._mlx_available:
            optimizations["mlx_acceleration"] = "enabled"
            optimizations["apple_silicon"] = "optimized"
        
        # Metal optimizations
        optimizations["metal_acceleration"] = "available"
        
        # macOS-specific performance settings
        macos_config = getattr(self.config, 'macos', {})
        performance_config = macos_config.get('performance', {})
        
        if performance_config.get('metal_acceleration', True):
            optimizations["metal_enabled"] = True
        
        if performance_config.get('mlx_optimization', True) and self._mlx_available:
            optimizations["mlx_optimization"] = True
        
        # Set thread count for Ollama if specified
        ollama_threads = performance_config.get('ollama_threads', 0)
        if ollama_threads > 0:
            import os
            os.environ['OLLAMA_NUM_THREAD'] = str(ollama_threads)
            optimizations["ollama_threads"] = ollama_threads
        
        return optimizations
    
    async def cleanup(self):
        """Clean up macOS native services"""
        # Native services typically don't need explicit cleanup
        # Ollama can keep running in background
        logger.info("macOS native services cleanup complete")
    
    def get_health_info(self) -> Dict[str, Any]:
        """Get macOS-specific health information"""
        base_health = super().get_health_info()
        base_health.update({
            "mlx_available": self._mlx_available,
            "native_services": self._native_services,
            "service_urls": {
                "ollama": "http://localhost:11434"
            },
            "apple_silicon": self._mlx_available,
            "tts_service": getattr(self.config.tts, 'service', 'macos')
        })
        return base_health