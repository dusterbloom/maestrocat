"""
Pipeline Extension Points - Decoupled hooks for module integration
"""
from enum import Enum
from typing import Dict, List, Callable, Any, Optional
import asyncio
import logging
from functools import wraps

from ..context.pipeline_context import PipelineContext

logger = logging.getLogger(__name__)


class ExtensionPoint(Enum):
    """
    Well-defined extension points in the pipeline where modules can hook in.
    
    Each point represents a specific stage in the voice agent pipeline.
    """
    # Audio input pipeline
    PRE_VAD = "pre_vad"              # Before voice activity detection
    POST_VAD = "post_vad"            # After voice activity detection
    PRE_STT = "pre_stt"              # Before speech-to-text
    POST_STT = "post_stt"            # After speech-to-text
    
    # LLM pipeline
    PRE_LLM = "pre_llm"              # Before LLM processing
    LLM_STREAMING = "llm_streaming"   # During LLM token generation
    POST_LLM = "post_llm"            # After LLM response complete
    
    # Audio output pipeline
    PRE_TTS = "pre_tts"              # Before text-to-speech
    TTS_STREAMING = "tts_streaming"   # During TTS audio generation
    POST_TTS = "post_tts"            # After TTS complete
    
    # Special events
    INTERRUPTION = "interruption"     # When user interrupts
    ERROR = "error"                   # When an error occurs
    PIPELINE_START = "pipeline_start" # When pipeline starts
    PIPELINE_END = "pipeline_end"     # When pipeline ends
    
    @classmethod
    def get_pipeline_order(cls) -> List['ExtensionPoint']:
        """Get the typical order of extension points in the pipeline"""
        return [
            cls.PIPELINE_START,
            cls.PRE_VAD,
            cls.POST_VAD,
            cls.PRE_STT,
            cls.POST_STT,
            cls.PRE_LLM,
            cls.LLM_STREAMING,
            cls.POST_LLM,
            cls.PRE_TTS,
            cls.TTS_STREAMING,
            cls.POST_TTS,
            cls.PIPELINE_END
        ]


class ExtensionHandler:
    """Wrapper for extension handlers with metadata"""
    
    def __init__(self, 
                 handler: Callable,
                 module_name: str,
                 priority: int = 50,
                 timeout: Optional[float] = None):
        self.handler = handler
        self.module_name = module_name
        self.priority = priority  # Lower numbers run first
        self.timeout = timeout
        self.enabled = True
        
    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Execute the handler with timeout protection"""
        if not self.enabled:
            return context
            
        try:
            if self.timeout:
                return await asyncio.wait_for(
                    self.handler(context),
                    timeout=self.timeout
                )
            else:
                return await self.handler(context)
        except asyncio.TimeoutError:
            logger.error(f"Handler {self.module_name} timed out at {self.timeout}s")
            return context
        except Exception as e:
            logger.error(f"Handler {self.module_name} failed: {e}")
            return context


class ExtensionManager:
    """
    Manages extension points in the pipeline.
    
    This manager:
    - Registers handlers for extension points
    - Executes handlers in priority order
    - Handles errors and timeouts gracefully
    - Provides metrics on extension execution
    """
    
    def __init__(self):
        self.hooks: Dict[ExtensionPoint, List[ExtensionHandler]] = {
            point: [] for point in ExtensionPoint
        }
        self.metrics: Dict[str, Dict[str, float]] = {}
        
    def register_hook(self, 
                     point: ExtensionPoint, 
                     handler: Callable,
                     module_name: str,
                     priority: int = 50,
                     timeout: Optional[float] = None):
        """
        Register a handler for an extension point
        
        Args:
            point: The extension point to hook into
            handler: Async function that takes and returns PipelineContext
            module_name: Name of the module registering the handler
            priority: Execution priority (lower runs first)
            timeout: Optional timeout in seconds
        """
        wrapper = ExtensionHandler(handler, module_name, priority, timeout)
        self.hooks[point].append(wrapper)
        
        # Sort by priority
        self.hooks[point].sort(key=lambda h: h.priority)
        
        logger.info(f"Registered hook for {module_name} at {point.value} with priority {priority}")
        
    def unregister_hook(self, point: ExtensionPoint, module_name: str):
        """Remove all handlers for a module at a specific extension point"""
        self.hooks[point] = [
            h for h in self.hooks[point] 
            if h.module_name != module_name
        ]
        logger.info(f"Unregistered hooks for {module_name} at {point.value}")
        
    def unregister_module(self, module_name: str):
        """Remove all handlers for a module across all extension points"""
        for point in ExtensionPoint:
            self.unregister_hook(point, module_name)
            
    async def execute_hooks(self, 
                          point: ExtensionPoint, 
                          context: PipelineContext) -> PipelineContext:
        """
        Execute all handlers for an extension point
        
        Args:
            point: The extension point being executed
            context: The current pipeline context
            
        Returns:
            Modified pipeline context after all handlers
        """
        handlers = self.hooks.get(point, [])
        if not handlers:
            return context
            
        logger.debug(f"Executing {len(handlers)} handlers for {point.value}")
        
        # Execute handlers in order
        for handler in handlers:
            start_time = asyncio.get_event_loop().time()
            context = await handler.execute(context)
            elapsed = asyncio.get_event_loop().time() - start_time
            
            # Track metrics
            if handler.module_name not in self.metrics:
                self.metrics[handler.module_name] = {}
            self.metrics[handler.module_name][point.value] = elapsed
            
        return context
        
    def get_registered_handlers(self, point: Optional[ExtensionPoint] = None) -> Dict[str, List[str]]:
        """
        Get information about registered handlers
        
        Args:
            point: Optional specific extension point to query
            
        Returns:
            Dictionary mapping extension points to handler module names
        """
        if point:
            return {
                point.value: [h.module_name for h in self.hooks.get(point, [])]
            }
            
        return {
            p.value: [h.module_name for h in self.hooks.get(p, [])]
            for p in ExtensionPoint
            if self.hooks.get(p)
        }
        
    def get_metrics(self) -> Dict[str, Dict[str, float]]:
        """Get execution time metrics for all handlers"""
        return self.metrics.copy()
        
    def enable_handler(self, module_name: str, point: Optional[ExtensionPoint] = None):
        """Enable handlers for a module"""
        for p in ([point] if point else ExtensionPoint):
            for handler in self.hooks.get(p, []):
                if handler.module_name == module_name:
                    handler.enabled = True
                    
    def disable_handler(self, module_name: str, point: Optional[ExtensionPoint] = None):
        """Disable handlers for a module"""
        for p in ([point] if point else ExtensionPoint):
            for handler in self.hooks.get(p, []):
                if handler.module_name == module_name:
                    handler.enabled = False


def extension_point(point: ExtensionPoint):
    """
    Decorator for marking methods as extension point handlers
    
    Usage:
        @extension_point(ExtensionPoint.POST_STT)
        async def handle_transcription(self, context: PipelineContext) -> PipelineContext:
            # Process transcription
            return context
    """
    def decorator(func):
        func._extension_point = point
        return func
    return decorator