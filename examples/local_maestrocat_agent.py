# examples/local_maestrocat_agent.py
"""
MaestroCat agent example using local services:
- WhisperLive for STT
- Ollama for LLM
- Kokoro/Piper for TTS
"""

import asyncio
import logging
import os
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

# MaestroCat imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from core.processors import (
    InterruptionHandler,
    MetricsCollector,
    EventEmitter,
    ModuleLoader
)
from core.services import (
    WhisperLiveSTTService,
    KokoroTTSService
)
# Monkey-patch fix for OLLamaLLMService api_key conflict bug in Pipecat 0.0.76
import pipecat.services.ollama.llm as _ollama
from pipecat.services.openai.base_llm import BaseOpenAILLMService

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

from pipecat.services.ollama.llm import OLLamaLLMService
from core.utils import MaestroCatConfig
from core.modules import VoiceRecognitionModule, MemoryModule
from core.apps.debug_ui import DebugUIServer
from core.serializers import RawAudioSerializer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LocalMaestroCatAgent:
    """Local MaestroCat agent using WhisperLive, Ollama, and Kokoro/Piper"""
    
    def __init__(self, config_file: str = "config/maestrocat.yaml"):
        self.config = MaestroCatConfig.from_file(config_file)
        self.pipeline = None
        self.runner = None
        
        # Components
        self.event_emitter = None
        self.metrics_collector = None
        self.module_loader = None
        
    async def setup(self):
        """Set up the voice agent pipeline"""
        
        # Create event system (disable emit_as_frames to avoid frame ordering issues)
        self.event_emitter = EventEmitter(buffer_size=1000, emit_as_frames=False)
        
        # Create metrics collector
        self.metrics_collector = MetricsCollector(
            emit_interval=5.0  # Emit metrics every 5 seconds
        )
        
        # Create and configure debug UI
        self.debug_ui = DebugUIServer(port=8080)
        self.debug_ui.attach_event_emitter(self.event_emitter)
        self.debug_ui.attach_config(self.config)
        
        # Create module loader
        self.module_loader = ModuleLoader(self.event_emitter)
        
        # Store transport params for WebSocket creation
        self.transport_params = FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,  # WhisperLive expects 16kHz
            audio_out_sample_rate=16000,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    confidence=self.config.vad.energy_threshold,
                    start_secs=self.config.vad.min_speech_ms / 1000.0,  # Convert ms to seconds
                    stop_secs=self.config.vad.pause_ms / 1000.0,  # Convert ms to seconds
                    min_volume=0.01
                )
            ),
            serializer=RawAudioSerializer()
        )
        
        # Create STT service (WhisperLive)
        stt = WhisperLiveSTTService(
            host=self.config.stt.host,
            port=self.config.stt.port,
            language=self.config.stt.language,
            translate=self.config.stt.translate,
            model=self.config.stt.model,
            use_vad=False,  # Disable WhisperLive VAD, use Pipecat's VAD instead
            vad_threshold=0.3  # More sensitive VAD threshold
        )
        
        # Create LLM service (Ollama) - using official Pipecat pattern
        # The service automatically appends /v1 to base_url, so use raw Ollama URL
        ollama_base_url = self.config.llm.base_url + "/v1" if not "/v1" in self.config.llm.base_url else self.config.llm.base_url
        llm = OLLamaLLMService(
            model=self.config.llm.model,
            base_url=ollama_base_url
        )
        
        # Create TTS service (Kokoro)
        tts = KokoroTTSService(
            base_url=self.config.tts.base_url,
            voice=self.config.tts.voice,
            speed=self.config.tts.speed,
            sample_rate=self.config.tts.sample_rate
        )
        
        # Create interruption handler
        interruption_handler = InterruptionHandler(
            threshold=self.config.interruption.threshold,
            ack_delay=self.config.interruption.ack_delay
        )
        
        # Store services for pipeline creation
        self.stt = stt
        self.llm = llm 
        self.tts = tts
        self.interruption_handler = interruption_handler
        
        # Load initial modules
        await self._load_modules()
        
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
        context = OpenAILLMContext(messages=[
            {
                "role": "system",
                "content": "You are MaestroCat, a helpful AI voice assistant. Respond naturally and conversationally. Keep responses concise but engaging."
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
        app = FastAPI()
        
        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.handle_websocket(websocket)
            
        return app
    
    async def run(self):
        """Run the agent"""
        # Set up services
        await self.setup()
        
        app = self.create_app()
        
        logger.info("Local MaestroCat Agent started!")
        logger.info("=" * 50)
        logger.info(f"WebSocket server: ws://localhost:8765/ws")
        logger.info(f"Debug UI: http://localhost:8080")
        logger.info(f"STT: WhisperLive @ {self.config.stt.host}:{self.config.stt.port}")
        logger.info(f"LLM: Ollama {self.config.llm.model}")
        logger.info(f"TTS: Kokoro {self.config.tts.voice}")
        logger.info("=" * 50)
        
        # Run both servers concurrently
        websocket_config = uvicorn.Config(app, host="0.0.0.0", port=8765, log_level="info")
        websocket_server = uvicorn.Server(websocket_config)
        
        # Start debug UI and WebSocket servers concurrently
        await asyncio.gather(
            self.debug_ui.start(),  # Debug UI on port 8080
            websocket_server.serve()  # WebSocket server on port 8765
        )


async def main():
    agent = LocalMaestroCatAgent()
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())