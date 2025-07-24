# examples/local_maestrocat_macos.py
"""
MaestroCat agent example for macOS using native services:
- Pipecat MLX Whisper for STT (optimized for Apple Silicon)
- Native Ollama for LLM  
- macOS System TTS
"""

import asyncio
import logging
import os
import subprocess
import sys
from typing import Optional

# FastAPI imports
from fastapi import FastAPI, WebSocket
import uvicorn

# Pipecat imports
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
# Use our custom Ollama service with the api_key bug fix
from core.services.ollama_llm import OLLamaLLMService

# MaestroCat imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from core.processors import (
    InterruptionHandler,
    MetricsCollector,
    EventEmitter,
    ModuleLoader
)
from pipecat.services.whisper.stt import WhisperSTTServiceMLX, MLXModel
from core.services.macos_tts import MacOSTTSService, MacOSPyTTSx3Service
from core.utils import MaestroCatConfig
from core.modules import VoiceRecognitionModule, MemoryModule
from core.apps.debug_ui import DebugUIServer
from core.serializers import RawAudioSerializer

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class MacOSMaestroCatAgent:
    """MaestroCat agent for macOS using native services"""
    
    def __init__(self, config_file: str = "config/maestrocat_macos.yaml"):
        self.config = MaestroCatConfig.from_file(config_file)
        
        # Components
        self.event_emitter = None
        self.metrics_collector = None
        self.module_loader = None
        self.debug_ui = None
        
        # Services
        self.stt = None
        self.llm = None
        self.tts = None
        self.interruption_handler = None
        
    async def setup(self):
        """Set up the voice agent pipeline"""
        
        # Create event system
        self.event_emitter = EventEmitter(buffer_size=1000, emit_as_frames=False)
        
        # Create metrics collector
        self.metrics_collector = MetricsCollector(emit_interval=5.0)
        
        # Create and configure debug UI
        self.debug_ui = DebugUIServer(port=self.config.development.get('debug_port', 8080))
        self.debug_ui.attach_event_emitter(self.event_emitter)
        self.debug_ui.attach_config(self.config)
        
        # Create module loader
        self.module_loader = ModuleLoader(self.event_emitter)
        
        # Store transport params for WebSocket creation
        self.transport_params = FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=self.config.stt.sample_rate,
            audio_out_sample_rate=self.config.tts.sample_rate,
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
        
        # Create services
        await self._create_services()
        
        # Load initial modules
        await self._load_modules()
        
    async def _create_services(self):
        """Create STT, LLM, and TTS services based on configuration"""
        
        # Create STT service - Use Pipecat's MLX Whisper (optimized for Apple Silicon)
        stt_config = self.config.stt
        logger.info(f"Using Pipecat MLX Whisper STT service with model: {stt_config.model_size}")
        
        # Map model sizes to MLXModel enum values (only these models are available)
        model_mapping = {
            "tiny": MLXModel.TINY,
            "base": MLXModel.MEDIUM,  # Use medium as base fallback
            "small": MLXModel.MEDIUM,  # Use medium as small fallback
            "medium": MLXModel.MEDIUM,
            "large": MLXModel.LARGE_V3,
            "large-v3": MLXModel.LARGE_V3,
            "large-v3-turbo": MLXModel.LARGE_V3_TURBO,
            "distil-large-v3": MLXModel.DISTIL_LARGE_V3
        }
        
        model = model_mapping.get(stt_config.model_size, MLXModel.MEDIUM)
        
        self.stt = WhisperSTTServiceMLX(
            model=model,
            language=stt_config.language if stt_config.language != "auto" else None
        )
        
        # Create LLM service (native Ollama)
        llm_config = self.config.llm
        base_url = llm_config.base_url
        if not base_url.endswith('/v1'):
            base_url += '/v1'
            
        logger.info(f"Using native Ollama LLM: {llm_config.model}")
        self.llm = OLLamaLLMService(
            model=llm_config.model,
            base_url=base_url,
            api_key="ollama"  # Required by Pipecat but not used by Ollama
        )
        
        # Create TTS service
        tts_config = self.config.tts
        tts_service = tts_config.service
        
        if tts_service == 'macos':
            logger.info(f"Using macOS System TTS with voice: {tts_config.voice}")
            self.tts = MacOSTTSService(
                voice=tts_config.voice,
                rate=tts_config.rate,
                volume=tts_config.volume,
                sample_rate=tts_config.sample_rate
            )
        elif tts_service == 'pyttsx3':
            logger.info("Using PyTTSx3 TTS service")
            self.tts = MacOSPyTTSx3Service(
                voice_id=tts_config.voice_id,
                rate=tts_config.rate,
                volume=tts_config.volume,
                sample_rate=tts_config.sample_rate
            )
        else:
            # Fallback to Kokoro if available
            from core.services import KokoroTTSService
            logger.info("Using Kokoro TTS service")
            self.tts = KokoroTTSService(
                base_url=tts_config.base_url,
                voice=tts_config.voice,
                speed=tts_config.speed,
                sample_rate=tts_config.sample_rate
            )
        
        # Create interruption handler
        self.interruption_handler = InterruptionHandler(
            threshold=self.config.interruption.threshold,
            ack_delay=self.config.interruption.ack_delay
        )
        
    async def _load_modules(self):
        """Load configured modules"""
        # Load voice recognition module
        if self.config.modules.get("voice_recognition", {}).get("enabled", False):
            await self.module_loader.load_module(
                VoiceRecognitionModule,
                self.config.modules["voice_recognition"]
            )
            
        # Load memory module
        if self.config.modules.get("memory", {}).get("enabled", False):
            await self.module_loader.load_module(
                MemoryModule,
                self.config.modules["memory"]
            )
            
    async def create_pipeline(self, websocket: WebSocket):
        """Create pipeline for WebSocket connection"""
        # Create transport for this WebSocket
        transport = FastAPIWebsocketTransport(websocket, self.transport_params)
        
        # Create LLM context with system message
        system_prompt = self.config.llm.system_prompt
        
        context = OpenAILLMContext(messages=[
            {
                "role": "system",
                "content": system_prompt
            }
        ])
        
        # Create context aggregators using the LLM service
        context_aggregator = self.llm.create_context_aggregator(context)
        
        # Build the pipeline with proper context management
        pipeline = Pipeline([
            # Input
            transport.input(),
            
            # STT
            self.stt,
            
            # User context aggregation (TranscriptionFrame → LLM trigger)
            context_aggregator.user(),
            
            # LLM
            self.llm,
            
            # TTS
            self.tts,
            
            # Output
            transport.output(),
            
            # Assistant context aggregation (LLM response handling)
            context_aggregator.assistant(),
        ])
        
        return pipeline, transport
    
    async def handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection"""
        await websocket.accept()
        
        pipeline, transport = await self.create_pipeline(websocket)
        task = PipelineTask(pipeline)
        runner = PipelineRunner()
        
        logger.info(f"WebSocket connected: {websocket.client}")
        
        try:
            await runner.run(task)
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
        finally:
            logger.info(f"WebSocket disconnected: {websocket.client}")
    
    def create_app(self):
        """Create FastAPI app"""
        app = FastAPI(title="MaestroCat macOS Agent")
        
        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.handle_websocket(websocket)
            
        @app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "platform": "macOS",
                "services": {
                    "stt": type(self.stt).__name__,
                    "llm": type(self.llm).__name__,
                    "tts": type(self.tts).__name__
                }
            }
            
        return app
    
    async def run(self):
        """Run the agent"""
        # Set up services
        await self.setup()
        
        app = self.create_app()
        
        websocket_port = self.config.development.get('websocket_port', 8765)
        debug_port = self.config.development.get('debug_port', 8080)
        
        logger.info("MaestroCat macOS Agent started!")
        logger.info("=" * 60)
        logger.info(f"🖥️  Platform: macOS (Apple Silicon)")
        logger.info(f"🔊 WebSocket server: ws://localhost:{websocket_port}/ws")
        logger.info(f"🐛 Debug UI: http://localhost:{debug_port}")
        logger.info(f"❤️  Health check: http://localhost:{websocket_port}/health")
        logger.info("")
        logger.info(f"🎤 STT: {type(self.stt).__name__}")
        logger.info(f"🧠 LLM: {self.config.llm.model} (native Ollama)")
        logger.info(f"🗣️  TTS: {type(self.tts).__name__}")
        logger.info("=" * 60)
        logger.info("")
        logger.info("🚀 Ready for connections!")
        
        # Run both servers concurrently
        websocket_config = uvicorn.Config(
            app, 
            host="0.0.0.0", 
            port=websocket_port, 
            log_level="info"
        )
        websocket_server = uvicorn.Server(websocket_config)
        
        # Start debug UI and WebSocket servers concurrently
        await asyncio.gather(
            self.debug_ui.start(),  # Debug UI
            websocket_server.serve()  # WebSocket server
        )


def check_dependencies():
    """Check if required native services are available"""
    missing = []
    
    # Check Ollama
    try:
        import httpx
        response = httpx.get("http://localhost:11434/api/version", timeout=2.0)
        if response.status_code != 200:
            missing.append("Ollama not running")
    except:
        missing.append("Ollama not available (install with: brew install ollama)")
    
    # Check MLX is available (for Apple Silicon Whisper)
    try:
        import mlx
        logger.info("MLX framework available for Apple Silicon optimization")
    except ImportError:
        logger.warning("MLX not available - Whisper will use CPU fallback")
    
    # Check macOS say command
    try:
        subprocess.run(["which", "say"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        missing.append("macOS 'say' command not available")
    
    if missing:
        logger.error("Missing dependencies:")
        for dep in missing:
            logger.error(f"  - {dep}")
        logger.info("\nInstallation commands:")
        logger.info("  brew install ollama")
        logger.info("  pip install 'pipecat-ai[mlx-whisper]'  # Install MLX Whisper")
        logger.info("  ollama serve  # Start Ollama server")
        logger.info("  ollama pull llama3.2:3b  # Download model")
        return False
        
    return True


async def main():
    if not check_dependencies():
        return
        
    agent = MacOSMaestroCatAgent()
    await agent.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise