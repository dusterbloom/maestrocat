# examples/decoupled_module_example.py
"""
Example demonstrating the new decoupled module architecture
"""
import asyncio
import logging
from typing import Dict, Any
from semantic_version import Version

# Core imports
from core.services.module_service import ModuleService
from core.context.pipeline_context import PipelineContext, ContextScope
from core.modules.interface import ExtensionPoint

# Example module imports
from core.modules.examples.enhanced_memory_module import EnhancedMemoryModule
from core.modules.examples.pipeline_metrics_module import PipelineMetricsModule
from core.modules.examples.smart_interruption_module import SmartInterruptionModule

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MaestroCatPipelineSimulator:
    """
    Simulates a MaestroCat pipeline to demonstrate the new module system.
    
    This shows how modules can be:
    - Registered and loaded independently
    - Integrated through extension points
    - Communicate through shared context
    - Managed with full lifecycle control
    """
    
    def __init__(self):
        self.module_service = ModuleService.get_instance()
        self.pipeline_context = self.module_service.get_pipeline_context()
        
        # Simulate pipeline components
        self.is_running = False
        self.request_count = 0
    
    async def setup(self) -> bool:
        """Set up the pipeline with modules"""
        try:
            logger.info("Setting up MaestroCat pipeline with new module system")
            
            # Register module classes
            self.module_service.register_module_class(EnhancedMemoryModule)
            self.module_service.register_module_class(PipelineMetricsModule)
            self.module_service.register_module_class(SmartInterruptionModule)
            
            logger.info("Registered module classes")
            
            # Load module instances with configurations
            memory_config = {
                "max_history": 50,
                "save_to_disk": True,
                "memory_file": "demo_memory.json",
                "context_window": 8,
                "enable_user_profiling": True
            }
            
            metrics_config = {
                "collection_interval": 2.0,
                "history_retention_hours": 1,
                "alert_thresholds": {
                    "stt_latency_ms": 800,
                    "llm_latency_ms": 2500,
                    "tts_latency_ms": 1500,
                    "total_latency_ms": 4000
                },
                "enable_detailed_logging": True
            }
            
            interruption_config = {
                "strategy": "context_aware",
                "base_threshold": 0.4,
                "learning_enabled": True,
                "continuation_enabled": True
            }
            
            # Load modules
            memory_instance = await self.module_service.load_module(
                "EnhancedMemoryModule", memory_config, "memory_main"
            )
            
            metrics_instance = await self.module_service.load_module(
                "PipelineMetricsModule", metrics_config, "metrics_main"
            )
            
            interruption_instance = await self.module_service.load_module(
                "SmartInterruptionModule", interruption_config, "interruption_main"
            )
            
            if not all([memory_instance, metrics_instance, interruption_instance]):
                logger.error("Failed to load all modules")
                return False
            
            logger.info(f"Loaded modules: {memory_instance}, {metrics_instance}, {interruption_instance}")
            
            # Start the module service
            success = await self.module_service.start()
            if not success:
                logger.error("Failed to start module service")
                return False
            
            logger.info("Module system setup completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set up pipeline: {e}")
            return False
    
    async def run_demo(self) -> None:
        """Run a demo conversation to show module integration"""
        logger.info("Starting pipeline demo...")
        
        try:
            self.is_running = True
            
            # Simulate conversation flow
            conversations = [
                {
                    "user_input": "Hello, how are you today?",
                    "assistant_response": "Hello! I'm doing well, thank you for asking. How can I help you today?"
                },
                {
                    "user_input": "Can you tell me about artificial intelligence?",
                    "assistant_response": "Artificial intelligence is a fascinating field that involves creating computer systems capable of performing tasks that typically require human intelligence, such as learning, reasoning, and problem-solving."
                },
                {
                    "user_input": "stop",  # This should trigger interruption
                    "assistant_response": "I was explaining AI concepts, but I'll stop here since you interrupted."
                },
                {
                    "user_input": "continue",  # This should trigger continuation
                    "assistant_response": "Continuing from where I left off - AI systems use various techniques like machine learning, neural networks, and deep learning to process information and make decisions."
                }
            ]
            
            for i, conv in enumerate(conversations):
                logger.info(f"\n--- Processing conversation {i+1} ---")
                await self._process_conversation_turn(conv["user_input"], conv["assistant_response"])
                
                # Add some delay between turns
                await asyncio.sleep(1)
            
            # Show final statistics
            await self._show_module_statistics()
            
        except Exception as e:
            logger.error(f"Error in demo: {e}")
        finally:
            self.is_running = False
    
    async def _process_conversation_turn(self, user_input: str, assistant_response: str) -> None:
        """Process a single conversation turn through the pipeline"""
        self.request_count += 1
        
        # Create mock transcription and response data
        from core.context.pipeline_context import TranscriptionData, LLMResponse
        
        transcription = TranscriptionData(
            text=user_input,
            confidence=0.95,
            language="en"
        )
        
        llm_response = LLMResponse(
            text=assistant_response,
            model="llama3.2:3b",
            tokens_used=len(assistant_response.split()) * 2  # Rough estimate
        )
        
        # Simulate pipeline stages with extension points
        
        # 1. PRE_STT
        logger.info("Stage: PRE_STT")
        self.pipeline_context = await self.module_service.execute_extension_point(
            ExtensionPoint.PRE_STT, self.pipeline_context
        )
        
        # Simulate STT processing time
        await asyncio.sleep(0.2)
        
        # 2. POST_STT
        logger.info(f"Stage: POST_STT - User said: '{user_input}'")
        self.pipeline_context.current_transcription = transcription
        self.pipeline_context = await self.module_service.execute_extension_point(
            ExtensionPoint.POST_STT, self.pipeline_context
        )
        
        # Check for interruption (simulate based on user input)
        if "stop" in user_input.lower() or "wait" in user_input.lower():
            logger.info("Interruption detected!")
            self.pipeline_context.set_interruption(True)
            self.pipeline_context = await self.module_service.execute_extension_point(
                ExtensionPoint.INTERRUPTION_DETECTED, self.pipeline_context
            )
            
            if self.pipeline_context.is_interrupted:
                logger.info("Processing interrupted, skipping to interruption handling")
                await self.module_service.execute_extension_point(
                    ExtensionPoint.INTERRUPTION_HANDLED, self.pipeline_context
                )
                return
        
        # 3. PRE_LLM
        logger.info("Stage: PRE_LLM")
        self.pipeline_context = await self.module_service.execute_extension_point(
            ExtensionPoint.PRE_LLM, self.pipeline_context
        )
        
        # Simulate LLM processing time
        await asyncio.sleep(0.8)
        
        # 4. POST_LLM
        logger.info(f"Stage: POST_LLM - Assistant responding: '{assistant_response[:50]}...'")
        self.pipeline_context.current_llm_response = llm_response
        self.pipeline_context = await self.module_service.execute_extension_point(
            ExtensionPoint.POST_LLM, self.pipeline_context
        )
        
        # 5. PRE_TTS
        logger.info("Stage: PRE_TTS")
        self.pipeline_context = await self.module_service.execute_extension_point(
            ExtensionPoint.PRE_TTS, self.pipeline_context
        )
        
        # Simulate TTS processing time
        await asyncio.sleep(0.5)
        
        # 6. POST_TTS
        logger.info("Stage: POST_TTS - Audio output ready")
        self.pipeline_context = await self.module_service.execute_extension_point(
            ExtensionPoint.POST_TTS, self.pipeline_context
        )
        
        # Reset request scope for next turn
        self.pipeline_context.reset_request_scope()
        
        logger.info(f"Conversation turn {self.request_count} completed")
    
    async def _show_module_statistics(self) -> None:
        """Show statistics from all loaded modules"""
        logger.info("\n=== MODULE STATISTICS ===")
        
        # Get all loaded modules
        modules = self.module_service.list_modules()
        
        for module_name, module_info in modules.items():
            logger.info(f"\nModule: {module_name}")
            logger.info(f"  Class: {module_info['class']}")
            logger.info(f"  State: {module_info['state']}")
            
            # Get module instance and show specific stats
            module = self.module_service.get_module(module_name)
            
            if module_name == "memory_main":
                # Memory module stats
                history = await module.get_conversation_history()
                logger.info(f"  Conversation history: {len(history)} messages")
                
                if hasattr(module, 'user_profiles'):
                    logger.info(f"  User profiles: {len(module.user_profiles)}")
            
            elif module_name == "metrics_main":
                # Metrics module stats
                stats = module.get_current_metrics()
                logger.info(f"  Requests processed: {stats.get('requests_processed', 0)}")
                logger.info(f"  Active requests: {stats.get('active_requests', 0)}")
                
                # Show latency stats if available
                for metric in ['stt_latency_ms', 'llm_latency_ms', 'tts_latency_ms', 'total_latency_ms']:
                    if metric in stats and stats[metric].get('count', 0) > 0:
                        logger.info(f"  {metric}: mean={stats[metric]['mean']:.1f}ms, "
                                  f"max={stats[metric]['max']:.1f}ms")
            
            elif module_name == "interruption_main":
                # Interruption module stats
                stats = module.get_interruption_statistics()
                logger.info(f"  Total interruptions: {stats.get('total_interruptions', 0)}")
                logger.info(f"  Current strategy: {stats.get('current_strategy', 'unknown')}")
                logger.info(f"  Continuation enabled: {stats.get('continuation_enabled', False)}")
        
        # Show overall pipeline context summary
        logger.info(f"\nPipeline Context Summary:")
        summary = self.pipeline_context.get_context_summary()
        logger.info(f"  Total messages: {summary['message_count']}")
        logger.info(f"  Conversation duration: {summary['conversation_duration']:.1f}s")
        logger.info(f"  Interruption count: {summary['interruption_count']}")
        logger.info(f"  Active modules: {len(summary['active_modules'])}")
    
    async def cleanup(self) -> None:
        """Clean up the pipeline and modules"""
        logger.info("Cleaning up pipeline...")
        
        try:
            # Stop the module service
            await self.module_service.stop()
            logger.info("Module service stopped")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


async def main():
    """Main demo function"""
    logger.info("MaestroCat Decoupled Module Architecture Demo")
    logger.info("=" * 50)
    
    pipeline = MaestroCatPipelineSimulator()
    
    try:
        # Set up the pipeline with modules
        success = await pipeline.setup()
        if not success:
            logger.error("Failed to set up pipeline")
            return
        
        # Run the demo
        await pipeline.run_demo()
        
        # Show module capabilities
        logger.info("\n=== MODULE CAPABILITIES ===")
        registry = pipeline.module_service.registry
        
        for module_name in registry.get_all_modules():
            module_info = registry.get_module_info(module_name)
            if module_info:
                metadata = module_info['metadata']
                logger.info(f"\n{metadata.name} v{metadata.version}:")
                logger.info(f"  Description: {metadata.description}")
                logger.info(f"  Capabilities: {[cap.value for cap in metadata.capabilities]}")
                logger.info(f"  Extension Points: {[ep.value for ep in metadata.extension_points]}")
                logger.info(f"  Dependencies: {metadata.dependencies}")
        
        # Demonstrate module reloading
        logger.info("\n=== DEMONSTRATING HOT RELOAD ===")
        success = await pipeline.module_service.reload_module("memory_main")
        logger.info(f"Memory module hot reload: {'SUCCESS' if success else 'FAILED'}")
        
        # Show final registry state
        logger.info("\n=== FINAL REGISTRY STATE ===")
        registry_dict = registry.to_dict()
        logger.info(f"Total modules registered: {len(registry_dict['modules'])}")
        logger.info(f"Available capabilities: {list(registry_dict['capability_index'].keys())}")
        logger.info(f"Available extension points: {list(registry_dict['extension_point_index'].keys())}")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise
    
    finally:
        await pipeline.cleanup()
    
    logger.info("\nDemo completed successfully!")
    logger.info("The new decoupled module architecture provides:")
    logger.info("- Independent module lifecycle management")
    logger.info("- Extension point based pipeline integration")
    logger.info("- Shared context for module communication")
    logger.info("- Hot reloading and dynamic module management")
    logger.info("- Dependency injection and versioning support")


if __name__ == "__main__":
    asyncio.run(main())