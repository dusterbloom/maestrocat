# examples/simple_maestrocat_agent.py
"""
Simple MaestroCat agent example that works with the current Pipecat version
"""

import asyncio
import logging
from typing import Optional

# Pipecat imports
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.services.openai import OpenAILLMService
from pipecat.services_elevenlabs import ElevenLabsTTSService
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.vad.silero import SileroVADAnalyzer

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
from core.utils import MaestroCatConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleMaestroCatAgent:
    """Simple MaestroCat agent example"""
    
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
            emit_interval=30.0
        )
        
        # Create module loader
        self.module_loader = ModuleLoader(self.event_emitter)
        
        # Create transport
        transport = FastAPIWebsocketTransport(
            host="localhost",
            port=8765,
            params=FastAPIWebsocketParams(
                audio_out_enabled=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer()
            )
        )
        
        # Create LLM service (using OpenAI for this example)
        llm = OpenAILLMService(
            api_key="YOUR_OPENAI_API_KEY",  # Replace with your actual API key
            model="gpt-3.5-turbo"
        )
        
        # Create TTS service (using ElevenLabs for this example)
        tts = ElevenLabsTTSService(
            api_key="YOUR_ELEVENLABS_API_KEY",  # Replace with your actual API key
            voice_id="YOUR_VOICE_ID"  # Replace with your actual voice ID
        )
        
        # Create LLM context and aggregator
        context = OpenAILLMContext(
            messages=[{
                "role": "system",
                "content": "You are a helpful AI assistant."
            }]
        )
        context_aggregator = llm.create_context_aggregator(context)
        
        # Create interruption handler
        interruption_handler = InterruptionHandler(
            threshold=0.2,
            ack_delay=0.05
        )
        
        # Build the pipeline
        self.pipeline = Pipeline([
            # Input
            transport.input(),
            
            # Event and metrics collection
            self.event_emitter,
            self.metrics_collector,
            
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
        
    async def run(self):
        """Run the agent"""
        # Set up pipeline
        await self.setup()
        
        # Create pipeline task
        task = PipelineTask(self.pipeline)
        
        logger.info("Simple MaestroCat Agent started!")
        logger.info("Connect to ws://localhost:8765")
        logger.info("Debug UI available at http://localhost:8080")
        
        # Run pipeline
        await self.runner.run(task)


async def main():
    agent = SimpleMaestroCatAgent()
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())