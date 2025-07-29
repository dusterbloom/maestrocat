#!/usr/bin/env python3
"""
MaestroCat Streaming Agent for macOS using whisper.cpp streaming STT.

This example demonstrates real-time streaming transcription using whisper.cpp's
streaming mode, providing continuous speech-to-text with minimal latency.
"""

import asyncio
import logging
import os
import sys
from typing import Optional

# FastAPI imports
from fastapi import FastAPI, WebSocket
import uvicorn

# Pipecat imports
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.frames.frames import TranscriptionFrame, Frame
from pipecat.processors.frame_processor import FrameProcessor

# MaestroCat imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from core.services.whispercpp_streaming_stt import WhisperCppStreamingSTTService
from core.services.ollama_llm import OLLamaLLMService
from core.services.macos_tts import MacOSTTSService
from core.transports.macos_stream_transport import MacOSStreamTransport
from core.utils import MaestroCatConfig
from core.apps.debug_ui import DebugUIServer
from core.processors import EventEmitter, MetricsCollector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MaestroCatStreamingAgent:
    """Real-time streaming agent using whisper.cpp streaming STT"""
    
    def __init__(self, config_file: str = "config/maestrocat_macos.yaml"):
        self.config = MaestroCatConfig.from_file(config_file)
        
        # Components
        self.event_emitter = None
        self.metrics_collector = None
        self.debug_ui = None
        
        # Services
        self.stt = None
        self.llm = None
        self.tts = None
        self.audio_transport = None
        
    async def setup(self):
        """Set up the streaming voice agent"""
        
        # Create event system
        self.event_emitter = EventEmitter(buffer_size=1000, emit_as_frames=False)
        
        # Create metrics collector
        self.metrics_collector = MetricsCollector(
            emit_interval=5.0, 
            event_emitter=self.event_emitter
        )
        
        # Create debug UI
        self.debug_ui = DebugUIServer(port=self.config.development.get('debug_port', 8080))
        self.debug_ui.attach_event_emitter(self.event_emitter)
        self.debug_ui.attach_config(self.config)
        
        # Create services
        await self._create_services()
        
    async def _create_services(self):
        """Create streaming STT, LLM, and TTS services"""
        
        # Create streaming STT service
        stt_config = self.config.stt
        logger.info(f"Using WhisperCpp streaming STT with model: {stt_config.model_path}")
        
        self.stt = WhisperCppStreamingSTTService(
            model_path=stt_config.model_path,
            model_size=stt_config.model_size,
            language=stt_config.language,
            sample_rate=stt_config.sample_rate,
            event_emitter=self.event_emitter
        )
        
        # Create LLM service (native Ollama)
        llm_config = self.config.llm
        logger.info(f"Using native Ollama LLM: {llm_config.model}")
        self.llm = OLLamaLLMService(
            model=llm_config.model,
            base_url=llm_config.base_url,
            temperature=llm_config.temperature,
            max_tokens=llm_config.max_tokens,
            top_p=llm_config.top_p,
            top_k=llm_config.top_k,
            event_emitter=self.event_emitter
        )
        
        # Create TTS service
        tts_config = self.config.tts
        logger.info(f"Using macOS System TTS with voice: {tts_config.voice}")
        self.tts = MacOSTTSService(
            voice=tts_config.voice,
            rate=tts_config.rate,
            volume=tts_config.volume,
            sample_rate=tts_config.sample_rate,
            event_emitter=self.event_emitter
        )
        
    async def start_streaming_mode(self):
        """Start real-time streaming mode with microphone input"""
        logger.info("Starting real-time streaming mode...")
        
        # Create audio transport for microphone input
        self.audio_transport = MacOSStreamTransport(
            stt_service=self.stt,
            sample_rate=self.config.stt.sample_rate,
            block_size=self.config.stt.get('block_size', 512)
        )
        
        # Start audio streaming
        success = self.audio_transport.start()
        if not success:
            logger.error("Failed to start audio streaming")
            return False
            
        logger.info("Real-time streaming started successfully")
        
        # Log streaming statistics
        stats = self.audio_transport.get_stats()
        logger.info(f"Streaming stats: {stats}")
        
        return True
        
    async def stop_streaming_mode(self):
        """Stop real-time streaming mode"""
        if self.audio_transport:
            self.audio_transport.stop()
            logger.info("Real-time streaming stopped")
            
    async def create_pipeline(self, websocket: WebSocket):
        """Create pipeline for WebSocket connection (streaming mode)"""
        # Create transport for this WebSocket
        transport = FastAPIWebsocketTransport(
            websocket,
            FastAPIWebsocketParams(
                audio_in_enabled=False,  # Audio comes from microphone
                audio_out_enabled=True,
                audio_out_sample_rate=self.config.tts.sample_rate,
                add_wav_header=False,
                vad_analyzer=SileroVADAnalyzer(
                    params=VADParams(
                        confidence=0.5,
                        start_secs=0.3,
                        stop_secs=0.8,
                        min_volume=0.01
                    )
                )
            )
        )
        
        # Create LLM context
        context = OpenAILLMContext(messages=[
            {
                "role": "system",
                "content": self.config.llm.system_prompt
            }
        ])
        
        # Create context aggregators
        context_aggregator = self.llm.create_context_aggregator(context)
        
        # Build the pipeline for streaming mode
        # Note: STT is handled by the streaming service directly
        pipeline = Pipeline([
            # Streaming STT (already receiving audio from microphone)
            self.stt,
            
            # Metrics collection
            self.metrics_collector,
            
            # User context aggregation
            context_aggregator.user(),
            
            # LLM
            self.llm,
            
            # TTS
            self.tts,
            
            # Output to WebSocket
            transport.output(),
            
            # Assistant context aggregation
            context_aggregator.assistant(),
        ])
        
        return pipeline, transport
        
    async def handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection for streaming mode"""
        await websocket.accept()
        
        pipeline, transport = await self.create_pipeline(websocket)
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
                enable_usage_metrics=True
            )
        )
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
        app = FastAPI(title="MaestroCat Streaming Agent")
        
        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.handle_websocket(websocket)
            
        @app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "platform": "macOS",
                "mode": "streaming",
                "services": {
                    "stt": "WhisperCppStreamingSTTService",
                    "llm": type(self.llm).__name__,
                    "tts": type(self.tts).__name__
                }
            }
            
        @app.post("/start_streaming")
        async def start_streaming():
            """Start real-time streaming mode"""
            success = await self.start_streaming_mode()
            return {"success": success}
            
        @app.post("/stop_streaming")
        async def stop_streaming():
            """Stop real-time streaming mode"""
            await self.stop_streaming_mode()
            return {"success": True}
            
        return app
        
    async def run(self):
        """Run the streaming agent"""
        # Set up services
        await self.setup()
        
        app = self.create_app()
        
        websocket_port = self.config.development.get('websocket_port', 8765)
        debug_port = self.config.development.get('debug_port', 8080)
        
        logger.info("MaestroCat Streaming Agent started!")
        logger.info("=" * 60)
        logger.info(f"🖥️  Platform: macOS (Apple Silicon)")
        logger.info(f"🎤 Streaming STT: Real-time whisper.cpp")
        logger.info(f"🧠 LLM: {self.config.llm.model} (native Ollama)")
        logger.info(f"🗣️  TTS: {type(self.tts).__name__}")
        logger.info(f"🔊 WebSocket: ws://localhost:{websocket_port}/ws")
        logger.info(f"🐛 Debug UI: http://localhost:{debug_port}")
        logger.info(f"❤️  Health: http://localhost:{websocket_port}/health")
        logger.info("=" * 60)
        logger.info("")
        logger.info("🚀 Ready for streaming mode!")
        logger.info("📞 POST /start_streaming to begin real-time transcription")
        logger.info("📞 POST /stop_streaming to stop real-time transcription")
        
        # Run both servers concurrently
        websocket_config = uvicorn.Config(
            app, 
            host="0.0.0.0", 
            port=websocket_port, 
            log_level="info"
        )
        websocket_server = uvicorn.Server(websocket_config)
        
        # Start debug UI and WebSocket servers
        await asyncio.gather(
            self.debug_ui.start(),
            websocket_server.serve()
        )


def check_dependencies():
    """Check if required services are available"""
    missing = []
    
    # Check Ollama
    try:
        import httpx
        response = httpx.get("http://localhost:11434/api/version", timeout=2.0)
        if response.status_code != 200:
            missing.append("Ollama not running")
    except:
        missing.append("Ollama not available (install with: brew install ollama)")
    
    # Check whisper.cpp stream binary
    stream_binary = "./bin/stream"
    if not os.path.exists(stream_binary):
        missing.append(
            f"whisper.cpp stream binary not found at {stream_binary}. "
            f"Run: ./build_whispercpp_stream.sh"
        )
    
    # Check model file
    model_path = os.path.expanduser("~/.cache/whisper/ggml-base.en.bin")
    if not os.path.exists(model_path):
        logger.warning(
            f"Whisper model not found at {model_path}. "
            f"Download with: wget https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin -P ~/.cache/whisper/"
        )
    
    if missing:
        logger.error("Missing dependencies:")
        for dep in missing:
            logger.error(f"  - {dep}")
        logger.info("\nInstallation commands:")
        logger.info("  ./build_whispercpp_stream.sh")
        logger.info("  brew install ollama")
        logger.info("  ollama serve")
        logger.info("  ollama pull llama3.2:3b")
        return False
        
    return True


async def main():
    if not check_dependencies():
        return
        
    agent = MaestroCatStreamingAgent()
    await agent.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise