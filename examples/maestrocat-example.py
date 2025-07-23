# examples/maestrocat_voice_agent.py
"""
Complete example of using MaestroCat with Pipecat
Shows how to build a voice agent with all the enhanced features
"""

import asyncio
import logging
import os
from typing import Optional

# Pipecat imports
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.transports.services.daily import DailyParams, DailyTransport
from pipecat.vad.silero import SileroVADAnalyzer
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

# MaestroCat imports
from core.processors import (
    InterruptionHandler,
    MetricsCollector,
    EventEmitter,
    ModuleLoader
)
from core.services import (
    WhisperLiveSTTService,
    OLLamaLLMService,
    KokoroTTSService
)
from core.utils import MaestroCatConfig
from core.modules import VoiceRecognitionModule, MemoryModule

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MaestroCatVoiceAgent:
    """Main voice agent application using MaestroCat + Pipecat"""
    
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
        
        # Create event system
        self.event_emitter = EventEmitter(buffer_size=1000)
        
        # Create metrics collector
        self.metrics_collector = MetricsCollector(
            emit_interval=30.0,
            event_callback=self._handle_metrics
        )
        
        # Create module loader
        self.module_loader = ModuleLoader(self.event_emitter)
        
        # Create transport (using Daily for this example)
        transport = DailyTransport(
            room_url=os.getenv("DAILY_ROOM_URL", ""),
            token=os.getenv("DAILY_TOKEN", ""),
            bot_name="MaestroCat",
            params=DailyParams(
                audio_out_enabled=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(
                    params={
                        "threshold": self.config.vad.energy_threshold,
                        "min_speech_duration_ms": self.config.vad.min_speech_ms,
                        "max_speech_duration_s": 30.0,
                        "min_silence_duration_ms": self.config.vad.pause_ms,
                    }
                )
            )
        )
        
        # Create STT service
        stt = WhisperLiveSTTService(
            host=self.config.stt.host,
            port=self.config.stt.port,
            language=self.config.stt.language,
            translate=self.config.stt.translate,
            model=self.config.stt.model,
            use_vad=self.config.stt.use_vad
        )
        
        # Create LLM service
        llm = OLLamaLLMService(
            base_url=self.config.llm.base_url,
            model=self.config.llm.model,
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens,
            top_p=self.config.llm.top_p,
            top_k=self.config.llm.top_k
        )
        
        # Create TTS service
        tts = KokoroTTSService(
            base_url=self.config.tts.base_url,
            voice=self.config.tts.voice,
            speed=self.config.tts.speed,
            sample_rate=self.config.tts.sample_rate
        )
        
        # Create LLM context and aggregator
        context = OpenAILLMContext(
            messages=[{
                "role": "system",
                "content": self.config.llm.system_prompt
            }]
        )
        context_aggregator = llm.create_context_aggregator(context)
        
        # Create interruption handler
        interruption_handler = InterruptionHandler(
            threshold=self.config.interruption.threshold,
            ack_delay=self.config.interruption.ack_delay,
            event_callback=self._handle_interruption
        )
        
        # Build the pipeline
        self.pipeline = Pipeline([
            # Input
            transport.input(),
            
            # Event and metrics collection
            self.event_emitter,
            self.metrics_collector,
            
            # STT
            stt,
            
            # Context aggregation for user
            context_aggregator.user(),
            
            # Interruption handling
            interruption_handler,
            
            # LLM
            llm,
            
            # Context aggregation for assistant
            context_aggregator.assistant(),
            
            # TTS
            tts,
            
            # Module processing
            self.module_loader,
            
            # Output
            transport.output()
        ])
        
        # Create runner
        self.runner = PipelineRunner()
        
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
            
    def _handle_metrics(self, event_type: str, data: dict):
        """Handle metrics events"""
        logger.info(f"Metrics: {data}")
        
    def _handle_interruption(self, event_type: str, data: dict):
        """Handle interruption events"""
        ratio = data.get("completion_ratio", 0)
        logger.info(f"Interruption at {ratio:.0%} completion")
        
    async def run(self):
        """Run the voice agent"""
        # Set up pipeline
        await self.setup()
        
        # Create pipeline task
        task = PipelineTask(self.pipeline)
        
        logger.info("MaestroCat Voice Agent started!")
        logger.info("=" * 60)
        logger.info(f"STT: WhisperLive @ {self.config.stt.host}:{self.config.stt.port}")
        logger.info(f"LLM: Ollama {self.config.llm.model}")
        logger.info(f"TTS: Kokoro {self.config.tts.voice}")
        logger.info("=" * 60)
        
        # Run pipeline
        await self.runner.run(task)
