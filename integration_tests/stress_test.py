# integration_tests/stress_test.py
"""Stress test for MaestroCat pipeline to evaluate performance under load"""

import asyncio
import time
import json
import statistics
from typing import List, Dict, Any
import logging
import random

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


class StressTestRunner:
    """Runs stress tests on MaestroCat pipeline"""
    
    def __init__(self, config_file: str = "config/maestrocat.yaml"):
        self.config = MaestroCatConfig.from_file(config_file)
        self.metrics_collector = None
        self.metrics_data = []
        self.test_results = {}
        
    def _handle_metrics(self, event_type: str, data: Dict[str, Any]):
        """Collect metrics data"""
        if event_type == "metrics":
            self.metrics_data.append(data)
            logger.debug(f"Collected metrics: {data}")
            
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
            emit_interval=0.5,  # Emit metrics more frequently during stress test
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
        
    async def run_stress_test(self, 
                              concurrent_requests: int = 10, 
                              duration_seconds: int = 30,
                              input_texts: List[str] = None) -> Dict[str, Any]:
        """Run stress test with concurrent requests for specified duration"""
        if input_texts is None:
            input_texts = [
                "Hello, how are you?",
                "What's the weather like today?",
                "Tell me a joke",
                "What is the capital of France?",
                "How does photosynthesis work?",
                "Explain quantum computing",
                "What's your favorite color?",
                "How do I make pasta?",
                "Why is the sky blue?",
                "What's the time?"
            ]
        
        logger.info(f"Running stress test: {concurrent_requests} concurrent requests for {duration_seconds}s")
        
        # Set up pipeline
        pipeline = await self.setup_pipeline()
        runner = PipelineRunner()
        task = PipelineTask(pipeline)
        
        # Track metrics
        request_times = []
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        # Concurrent request handler
        async def send_request():
            while time.time() < end_time:
                # Select random input text
                text = random.choice(input_texts)
                
                # Time the request
                req_start = time.time()
                
                try:
                    # Send the request
                    from pipecat.processors.frame_processor import FrameDirection
                    await pipeline.process_frame(TextFrame(text), FrameDirection.DOWNSTREAM)
                    
                    # Record time
                    req_end = time.time()
                    request_times.append(req_end - req_start)
                except Exception as e:
                    logger.error(f"Request failed: {e}")
                
                # Small delay to prevent overwhelming
                await asyncio.sleep(0.1)
        
        # Start the pipeline runner in background
        runner_task = asyncio.create_task(runner.run(task))
        
        # Start concurrent requests
        request_tasks = [asyncio.create_task(send_request()) for _ in range(concurrent_requests)]
        
        # Wait for duration to complete
        await asyncio.sleep(duration_seconds)
        
        # Cancel runner task (as it runs indefinitely)
        runner_task.cancel()
        
        # Cancel request tasks
        for t in request_tasks:
            t.cancel()
        
        # Calculate statistics
        if request_times:
            avg_time = statistics.mean(request_times)
            min_time = min(request_times)
            max_time = max(request_times)
            std_dev = statistics.stdev(request_times) if len(request_times) > 1 else 0
            total_requests = len(request_times)
            requests_per_second = total_requests / duration_seconds
        else:
            avg_time = min_time = max_time = std_dev = 0
            total_requests = 0
            requests_per_second = 0
        
        # Store results
        self.test_results = {
            "concurrent_requests": concurrent_requests,
            "duration_seconds": duration_seconds,
            "total_requests": total_requests,
            "requests_per_second": requests_per_second,
            "average_time": avg_time,
            "min_time": min_time,
            "max_time": max_time,
            "std_deviation": std_dev,
            "request_times": request_times,
            "collected_metrics": self.metrics_data
        }
        
        logger.info(f"Stress test completed. Requests/sec: {requests_per_second:.2f}")
        return self.test_results
        
    def print_results(self):
        """Print formatted stress test results"""
        if not self.test_results:
            logger.warning("No test results to display")
            return
            
        print("\n" + "="*60)
        print("STRESS TEST RESULTS")
        print("="*60)
        print(f"Concurrent Requests: {self.test_results['concurrent_requests']}")
        print(f"Duration: {self.test_results['duration_seconds']}s")
        print("-"*60)
        print(f"Total Requests: {self.test_results['total_requests']}")
        print(f"Requests/Second: {self.test_results['requests_per_second']:.2f}")
        print("-"*60)
        print(f"Average Response Time: {self.test_results['average_time']:.3f}s")
        print(f"Min Response Time: {self.test_results['min_time']:.3f}s")
        print(f"Max Response Time: {self.test_results['max_time']:.3f}s")
        print(f"Standard Deviation: {self.test_results['std_deviation']:.3f}s")
        print("-"*60)
        
        # Print collected metrics if available
        if self.test_results['collected_metrics']:
            print("Component Metrics (latest sample):")
            latest_metrics = self.test_results['collected_metrics'][-1]
            for component, latency in latest_metrics.get('component_timings', {}).items():
                print(f"  {component.upper()}: {latency:.1f}ms")
            print(f"  TOTAL LATENCY: {latest_metrics.get('total_latency_ms', 0):.1f}ms")
        print("="*60 + "\n")


async def main():
    """Main stress test function"""
    # Create test runner
    test_runner = StressTestRunner()
    
    # Define test scenarios
    test_scenarios = [
        {"concurrent_requests": 5, "duration": 15},
        {"concurrent_requests": 10, "duration": 15},
        {"concurrent_requests": 15, "duration": 15}
    ]
    
    # Run tests for each scenario
    for scenario in test_scenarios:
        try:
            await test_runner.run_stress_test(
                concurrent_requests=scenario["concurrent_requests"],
                duration_seconds=scenario["duration"]
            )
            test_runner.print_results()
        except Exception as e:
            logger.error(f"Error running stress test: {e}")
        
        # Wait between test scenarios
        await asyncio.sleep(3)
    
    logger.info("All stress tests completed")


if __name__ == "__main__":
    asyncio.run(main())