# integration_tests/latency_test.py
"""Integration test to measure latency in MaestroCat pipeline"""

import asyncio
import time
import json
import statistics
from typing import List, Dict, Any
import logging

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.transports.local.audio import LocalAudioTransportParams
from pipecat.frames.frames import TextFrame

from core.transports.wsl_audio_transport import WSLAudioTransport
from core.processors.interruption import MetricsCollector
from core.services.ollama_llm import OLLamaLLMService
from core.services.whisperlive_stt import WhisperLiveSTTService
from core.services.kokoro_tts import KokoroTTSService
from core.utils.config import MaestroCatConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LatencyTestRunner:
    """Runs latency tests on MaestroCat pipeline"""
    
    def __init__(self, config_file: str = "config/maestrocat.yaml"):
        self.config = MaestroCatConfig.from_file(config_file)
        self.metrics_collector = None
        self.metrics_data = []
        self.test_results = {}
        
    def _handle_metrics(self, event_type: str, data: Dict[str, Any]):
        """Collect metrics data"""
        if event_type == "metrics":
            self.metrics_data.append(data)
            logger.info(f"Collected metrics: {data}")
            
    async def setup_pipeline(self):
        """Set up the test pipeline with metrics collection"""
        # Create transport (with no audio for testing)
        transport = WSLAudioTransport(
            params=LocalAudioTransportParams(
                audio_in_enabled=False,
                audio_out_enabled=False,
            )
        )
        
        # Create metrics collector
        self.metrics_collector = MetricsCollector(
            emit_interval=1.0,  # Emit metrics every second
            event_callback=self._handle_metrics
        )
        
        # Create services
        stt = WhisperLiveSTTService(
            host=self.config.stt.host,
            port=self.config.stt.port,
            language=self.config.stt.language,
            translate=self.config.stt.translate,
            model=self.config.stt.model,
            use_vad=self.config.stt.use_vad
        )
        
        llm = OLLamaLLMService(
            base_url=self.config.llm.base_url,
            model=self.config.llm.model,
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens,
            top_p=self.config.llm.top_p,
            top_k=self.config.llm.top_k
        )
        
        tts = KokoroTTSService(
            base_url=self.config.tts.base_url,
            voice=self.config.tts.voice,
            speed=self.config.tts.speed,
            sample_rate=self.config.tts.sample_rate
        )
        
        # Create LLM context
        context = OpenAILLMContext(
            messages=[{
                "role": "system",
                "content": self.config.llm.system_prompt
            }]
        )
        context_aggregator = llm.create_context_aggregator(context)
        
        # Build pipeline
        pipeline = Pipeline([
            transport.input(),
            self.metrics_collector,
            stt,
            context_aggregator.user(),
            llm,
            context_aggregator.assistant(),
            tts,
            transport.output()
        ])
        
        return pipeline
        
    async def run_latency_test(self, test_input: str, iterations: int = 5) -> Dict[str, Any]:
        """Run latency test with specified input"""
        logger.info(f"Running latency test with input: '{test_input}' for {iterations} iterations")
        
        # Set up pipeline
        pipeline = await self.setup_pipeline()
        runner = PipelineRunner()
        task = PipelineTask(pipeline)
        
        # Store timing results
        iteration_results = []
        
        # Run test iterations
        for i in range(iterations):
            logger.info(f"Running iteration {i+1}/{iterations}")
            
            # Clear previous metrics
            self.metrics_data = []
            
            # Start timing
            start_time = time.time()
            
            # Send test input
            await pipeline.process_frame(TextFrame(test_input))
            
            # Run for a short duration to capture response
            try:
                await asyncio.wait_for(runner.run(task), timeout=10.0)
            except asyncio.TimeoutError:
                pass
            
            # End timing
            end_time = time.time()
            
            # Calculate iteration time
            iteration_time = end_time - start_time
            iteration_results.append(iteration_time)
            
            # Wait between iterations
            await asyncio.sleep(1)
            
        # Calculate statistics
        avg_time = statistics.mean(iteration_results)
        min_time = min(iteration_results)
        max_time = max(iteration_results)
        std_dev = statistics.stdev(iteration_results) if len(iteration_results) > 1 else 0
        
        # Store results
        self.test_results = {
            "input": test_input,
            "iterations": iterations,
            "average_time": avg_time,
            "min_time": min_time,
            "max_time": max_time,
            "std_deviation": std_dev,
            "individual_times": iteration_results,
            "collected_metrics": self.metrics_data
        }
        
        logger.info(f"Test completed. Average time: {avg_time:.3f}s")
        return self.test_results
        
    def print_results(self):
        """Print formatted test results"""
        if not self.test_results:
            logger.warning("No test results to display")
            return
            
        print("\n" + "="*60)
        print("LATENCY TEST RESULTS")
        print("="*60)
        print(f"Input: {self.test_results['input']}")
        print(f"Iterations: {self.test_results['iterations']}")
        print("-"*60)
        print(f"Average Time: {self.test_results['average_time']:.3f}s")
        print(f"Min Time: {self.test_results['min_time']:.3f}s")
        print(f"Max Time: {self.test_results['max_time']:.3f}s")
        print(f"Standard Deviation: {self.test_results['std_deviation']:.3f}s")
        print("-"*60)
        print("Individual Times:")
        for i, t in enumerate(self.test_results['individual_times']):
            print(f"  Iteration {i+1}: {t:.3f}s")
        print("-"*60)
        
        # Print collected metrics if available
        if self.test_results['collected_metrics']:
            print("Component Metrics:")
            latest_metrics = self.test_results['collected_metrics'][-1]
            for component, latency in latest_metrics.get('component_timings', {}).items():
                print(f"  {component.upper()}: {latency:.1f}ms")
            print(f"  TOTAL LATENCY: {latest_metrics.get('total_latency_ms', 0):.1f}ms")
        print("="*60 + "\n")


async def main():
    """Main test function"""
    # Create test runner
    test_runner = LatencyTestRunner()
    
    # Define test inputs
    test_inputs = [
        "Hello, how are you today?",
        "What's the weather like?",
        "Tell me a joke",
        "What is the capital of France?",
        "How does photosynthesis work?"
    ]
    
    # Run tests for each input
    for test_input in test_inputs:
        try:
            await test_runner.run_latency_test(test_input, iterations=3)
            test_runner.print_results()
        except Exception as e:
            logger.error(f"Error running test for '{test_input}': {e}")
        
        # Wait between test sets
        await asyncio.sleep(2)
    
    logger.info("All latency tests completed")


if __name__ == "__main__":
    asyncio.run(main())