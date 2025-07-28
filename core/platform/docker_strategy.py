"""
Docker Platform Strategy

Implements platform strategy for Docker-based services including:
- WhisperLive STT (GPU/CPU variants)
- Ollama LLM (Docker container)
- Kokoro TTS (GPU/CPU variants)
- Docker service management and health checking
"""

import asyncio
import subprocess
import logging
from typing import Any, Dict, List, Tuple

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.transports.network.fastapi_websocket import FastAPIWebsocketParams

from .strategy import PlatformStrategy, PlatformType, PlatformInfo, PlatformCapabilities, ServiceSpecs
from ..services import WhisperLiveSTTService, KokoroTTSService
from ..serializers import RawAudioSerializer

# Apply Ollama monkey patch for Docker strategy
import pipecat.services.ollama.llm as _ollama
from pipecat.services.openai.base_llm import BaseOpenAILLMService

# Store original methods if not already patched
if not hasattr(_ollama.OLLamaLLMService, '_maestrocat_patched'):
    _orig_init = _ollama.OLLamaLLMService.__init__
    _orig_create_client = _ollama.OLLamaLLMService.create_client

    def fixed_init(self, *, model="llama3.2:3b", base_url="http://localhost:11434/v1", **kwargs):
        # Remove api_key if passed in kwargs to avoid duplicate argument error
        kwargs.pop("api_key", None)
        return _orig_init(self, model=model, base_url=base_url, **kwargs)

    def fixed_create_client(self, base_url=None, **kwargs):
        # Remove api_key from kwargs to avoid conflict
        kwargs.pop("api_key", None)
        # Call grandparent's create_client directly to bypass the broken super() call
        return BaseOpenAILLMService.create_client(self, api_key="ollama", base_url=base_url, **kwargs)

    _ollama.OLLamaLLMService.__init__ = fixed_init
    _ollama.OLLamaLLMService.create_client = fixed_create_client
    _ollama.OLLamaLLMService._maestrocat_patched = True

from pipecat.services.ollama.llm import OLLamaLLMService

logger = logging.getLogger(__name__)


class DockerPlatformStrategy(PlatformStrategy):
    """
    Platform strategy for Docker-based services.
    
    Handles:
    - Docker service lifecycle management
    - GPU vs CPU service selection
    - Service health monitoring
    - Platform-specific optimizations for Docker
    """
    
    def __init__(self, config: Any):
        super().__init__(config)
        self._docker_services_started = False
        self._gpu_available = None
    
    @property
    def platform_info(self) -> PlatformInfo:
        """Get Docker platform information"""
        # Lazy load capabilities
        if self._gpu_available is None:
            self._gpu_available = self._check_gpu_availability()
        
        capabilities = PlatformCapabilities(
            has_gpu=self._gpu_available,
            supports_metal=False,
            supports_mlx=False,
            docker_available=True,
            native_services=[]
        )
        
        description = "Docker services"
        if self._gpu_available:
            description += " (GPU-accelerated)"
        else:
            description += " (CPU-only)"
        
        return PlatformInfo(
            platform_type=PlatformType.DOCKER,
            capabilities=capabilities,
            description=description,
            recommended_models={
                "stt": "medium" if self._gpu_available else "base",
                "llm": "llama3.2:3b" if self._gpu_available else "llama3.2:1b",
                "tts": "af_bella"
            }
        )
    
    @property
    def service_specs(self) -> ServiceSpecs:
        """Get service specifications for Docker platform"""
        return ServiceSpecs(
            stt_service="WhisperLiveSTTService",
            llm_service="OLLamaLLMService", 
            tts_service="KokoroTTSService",
            transport_class="FastAPIWebsocketTransport",
            additional_processors=["MetricsCollector", "EventEmitter"]
        )
    
    def _check_gpu_availability(self) -> bool:
        """Check if NVIDIA GPU and nvidia-docker are available"""
        try:
            result = subprocess.run(
                ["nvidia-smi"], 
                capture_output=True, 
                check=True,
                timeout=5
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    async def check_dependencies(self) -> Tuple[bool, List[str]]:
        """Check Docker and service dependencies"""
        missing = []
        
        # Check Docker
        try:
            result = subprocess.run(
                ["docker", "--version"], 
                capture_output=True, 
                check=True,
                timeout=5
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            missing.append("Docker (install from: https://docker.com)")
        
        # Check Docker Compose
        compose_available = False
        try:
            result = subprocess.run(
                ["docker-compose", "--version"], 
                capture_output=True, 
                check=True,
                timeout=5
            )
            compose_available = True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            try:
                result = subprocess.run(
                    ["docker", "compose", "version"], 
                    capture_output=True, 
                    check=True,
                    timeout=5
                )
                compose_available = True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
        
        if not compose_available:
            missing.append("Docker Compose (install with: pip install docker-compose)")
        
        # Check if Docker daemon is running
        try:
            result = subprocess.run(
                ["docker", "ps"], 
                capture_output=True, 
                check=True,
                timeout=10
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            missing.append("Docker daemon not running (start Docker Desktop or run: sudo systemctl start docker)")
        
        self._dependencies_checked = True
        return len(missing) == 0, missing
    
    async def setup_services(self) -> bool:
        """Start Docker services using docker-compose"""
        if self._docker_services_started:
            return True
        
        logger.info("Starting Docker services...")
        
        # Determine compose files based on GPU availability
        if self._gpu_available is None:
            self._gpu_available = self._check_gpu_availability()
        
        if self._gpu_available:
            compose_files = [
                "docker-compose.yml", 
                "docker-compose.gpu.yml"
            ]
            logger.info("Using GPU-accelerated services")
        else:
            compose_files = [
                "docker-compose.yml",
                "docker-compose.cpu.yml"
            ]
            logger.info("Using CPU-only services")
        
        # Build docker-compose command
        cmd = ["docker-compose"]
        for file in compose_files:
            cmd.extend(["-f", file])
        cmd.extend(["up", "-d"])
        
        try:
            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                timeout=120  # Docker pulls can take time
            )
            
            if result.returncode == 0:
                logger.info("Docker services started successfully")
                
                # Wait for services to be ready
                await self._wait_for_services()
                
                self._docker_services_started = True
                return True
            else:
                logger.error(f"Failed to start Docker services: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Docker service startup timed out")
            return False
        except Exception as e:
            logger.error(f"Error starting Docker services: {e}")
            return False
    
    async def _wait_for_services(self, timeout: int = 60):
        """Wait for Docker services to be ready"""
        import httpx
        
        services = [
            ("WhisperLive STT", "ws://localhost:9090", self._check_websocket_health),
            ("Ollama LLM", "http://localhost:11434/api/version", self._check_http_health),
            ("Kokoro TTS", "http://localhost:5000/health", self._check_http_health)
        ]
        
        start_time = asyncio.get_event_loop().time()
        
        for service_name, url, health_check in services:
            logger.info(f"Waiting for {service_name} to be ready...")
            
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                try:
                    if await health_check(url):
                        logger.info(f"✅ {service_name} is ready")
                        break
                except Exception:
                    pass
                
                await asyncio.sleep(2)
            else:
                logger.warning(f"⚠️  {service_name} may not be ready (timeout)")
    
    async def _check_http_health(self, url: str) -> bool:
        """Check HTTP service health"""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=5.0)
                return response.status_code == 200
        except Exception:
            return False
    
    async def _check_websocket_health(self, url: str) -> bool:
        """Check WebSocket service health (simplified)"""
        # For now, just check if the port is open
        import socket
        try:
            host, port = url.replace("ws://", "").split(":")
            port = int(port)
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    async def create_stt_service(self, event_emitter=None):
        """Create WhisperLive STT service"""
        return WhisperLiveSTTService(
            host=self.config.stt.host,
            port=self.config.stt.port,
            language=self.config.stt.language,
            translate=self.config.stt.translate,
            model=self.config.stt.model,
            use_vad=False,  # Use Pipecat's VAD instead
            vad_threshold=0.3
        )
    
    async def create_llm_service(self, event_emitter=None):
        """Create Ollama LLM service"""
        # Ensure URL has /v1 suffix for OpenAI compatibility
        base_url = self.config.llm.base_url
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        
        return OLLamaLLMService(
            model=self.config.llm.model,
            base_url=base_url,
            temperature=getattr(self.config.llm, 'temperature', 0.7),
            max_tokens=getattr(self.config.llm, 'max_tokens', 1000)
        )
    
    async def create_tts_service(self, event_emitter=None):
        """Create Kokoro TTS service"""
        return KokoroTTSService(
            base_url=self.config.tts.base_url,
            voice=self.config.tts.voice,
            speed=getattr(self.config.tts, 'speed', 1.0),
            sample_rate=getattr(self.config.tts, 'sample_rate', 24000)
        )
    
    def create_transport_params(self) -> FastAPIWebsocketParams:
        """Create transport parameters optimized for Docker services"""
        return FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,  # WhisperLive expects 16kHz
            audio_out_sample_rate=24000,  # Kokoro outputs 24kHz
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
        """Get system prompt optimized for Docker platform performance"""
        base_prompt = getattr(self.config.llm, 'system_prompt', 
            "You are MaestroCat, a helpful AI voice assistant. "
            "Respond naturally and conversationally. Keep responses concise but engaging.")
        
        # Add Docker-specific guidance for performance
        if not self._gpu_available:
            base_prompt += " Please keep responses brief to ensure good performance on CPU-only systems."
        
        return base_prompt
    
    async def apply_platform_optimizations(self) -> Dict[str, Any]:
        """Apply Docker-specific optimizations"""
        optimizations = {}
        
        # Set Docker-specific environment variables if needed
        # This could include memory limits, CPU limits, etc.
        
        if self._gpu_available:
            optimizations["gpu_acceleration"] = "enabled"
            optimizations["cuda_memory_limit"] = "auto"
        else:
            optimizations["cpu_optimization"] = "enabled"
            optimizations["memory_limit"] = "conservative"
        
        return optimizations
    
    async def cleanup(self):
        """Clean up Docker services"""
        if self._docker_services_started:
            logger.info("Stopping Docker services...")
            try:
                result = subprocess.run(
                    ["docker-compose", "down"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    logger.info("Docker services stopped successfully")
                else:
                    logger.warning(f"Issues stopping Docker services: {result.stderr}")
            except Exception as e:
                logger.error(f"Error stopping Docker services: {e}")
            
            self._docker_services_started = False
    
    def get_health_info(self) -> Dict[str, Any]:
        """Get Docker-specific health information"""
        base_health = super().get_health_info()
        base_health.update({
            "docker_services_started": self._docker_services_started,
            "gpu_available": self._gpu_available,
            "service_urls": {
                "whisperlive": "ws://localhost:9090",
                "ollama": "http://localhost:11434",
                "kokoro": "http://localhost:5000"
            }
        })
        return base_health