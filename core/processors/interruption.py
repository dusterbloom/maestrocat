# maestrocat/processors/interruption.py
"""Smart interruption handler for Pipecat"""
import time
import asyncio
import json
from typing import Optional, Dict, Any
import logging

from pipecat.frames.frames import Frame, SystemFrame, TextFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

logger = logging.getLogger(__name__)


class InterruptionHandler(FrameProcessor):
    """
    Handles interruptions with context preservation
    Monitors TTS output and intelligently handles user interruptions
    """
    
    def __init__(
        self,
        threshold: float = 0.2,
        ack_delay: float = 0.05,
        event_callback: Optional[callable] = None
    ):
        super().__init__()
        self.threshold = threshold
        self.ack_delay = ack_delay
        self.event_callback = event_callback
        
        # TTS tracking
        self.tts_active = False
        self.tts_start_time = None
        self.tts_duration = None
        self.current_response = ""
        self.response_tokens = 0
        
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames to detect and handle interruptions"""
        
        # Track TTS state
        if isinstance(frame, SystemFrame):
            if frame.name == "tts_started":
                self.tts_active = True
                self.tts_start_time = time.time()
                self.tts_duration = frame.data.get("duration", 0) if hasattr(frame, 'data') else 0
                
            elif frame.name == "tts_stopped":
                self.tts_active = False
                
            # Handle interruption on new speech
            elif frame.name == "user_started_speaking" and self.tts_active:
                await self._handle_interruption()
                
        # Track response content
        elif isinstance(frame, TextFrame) and direction == FrameDirection.DOWNSTREAM:
            self.current_response = frame.text
            self.response_tokens = len(frame.text.split())
            
        await self.push_frame(frame, direction)
        
    async def _handle_interruption(self):
        """Handle user interruption intelligently"""
        if not self.tts_start_time or not self.tts_duration:
            completion_ratio = 0
        else:
            elapsed = time.time() - self.tts_start_time
            completion_ratio = elapsed / self.tts_duration if self.tts_duration > 0 else 0
            
        # Determine if we should preserve context
        preserve_context = completion_ratio < self.threshold
        
        # Stop TTS
        # Use TextFrame to signal TTS interruption
        await self.push_frame(TextFrame(json.dumps({"type": "interrupt_tts"})))
        
        # Log interruption
        logger.info(f"Interruption at {completion_ratio:.0%} completion")
        
        # Emit event if callback provided
        if self.event_callback:
            self.event_callback("interruption", {
                "completion_ratio": completion_ratio,
                "preserve_context": preserve_context,
                "elapsed_ms": (time.time() - self.tts_start_time) * 1000
            })
            
        # Add context marker
        context_marker = f"[INTERRUPTED at {completion_ratio:.0%}]" if preserve_context else "[INTERRUPTED]"
        await self.push_frame(TextFrame(context_marker))
        
        # Brief acknowledgment pause
        await asyncio.sleep(self.ack_delay)


# maestrocat/processors/metrics.py
"""Performance metrics collector for Pipecat pipelines"""
import time
from typing import Dict, Any, Optional
import logging
from dataclasses import dataclass, field

from pipecat.frames.frames import Frame, SystemFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
    """Container for pipeline performance metrics"""
    stt_latency: float = 0.0
    llm_latency: float = 0.0
    tts_latency: float = 0.0
    total_latency: float = 0.0
    frames_processed: int = 0
    errors: int = 0
    
    # Detailed timing
    component_timings: Dict[str, float] = field(default_factory=dict)
    

class MetricsCollector(FrameProcessor):
    """
    Collects performance metrics throughout the pipeline
    Emits metric events that can be consumed by monitoring systems
    """
    
    def __init__(
        self,
        emit_interval: float = 10.0,
        event_callback: Optional[callable] = None
    ):
        super().__init__()
        self.emit_interval = emit_interval
        self.event_callback = event_callback
        
        self.metrics = PipelineMetrics()
        self._component_starts: Dict[str, float] = {}
        self._last_emit_time = time.time()
        
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Track timing through the pipeline"""
        self.metrics.frames_processed += 1
        
        if isinstance(frame, SystemFrame):
            # Track component timing
            if frame.name.endswith("_start"):
                component = frame.name.replace("_start", "")
                self._component_starts[component] = time.time()
                
            elif frame.name.endswith("_end"):
                component = frame.name.replace("_end", "")
                if component in self._component_starts:
                    latency = (time.time() - self._component_starts[component]) * 1000
                    self.metrics.component_timings[component] = latency
                    
                    # Update specific metrics
                    if component == "stt":
                        self.metrics.stt_latency = latency
                    elif component == "llm":
                        self.metrics.llm_latency = latency
                    elif component == "tts":
                        self.metrics.tts_latency = latency
                        
                    # Calculate total
                    self.metrics.total_latency = sum([
                        self.metrics.stt_latency,
                        self.metrics.llm_latency,
                        self.metrics.tts_latency
                    ])
                    
            elif frame.name == "error":
                self.metrics.errors += 1
                
        # Emit metrics periodically
        current_time = time.time()
        if current_time - self._last_emit_time >= self.emit_interval:
            await self._emit_metrics()
            self._last_emit_time = current_time
            
        await self.push_frame(frame, direction)
        
    async def _emit_metrics(self):
        """Emit collected metrics"""
        metrics_data = {
            "stt_latency_ms": self.metrics.stt_latency,
            "llm_latency_ms": self.metrics.llm_latency,
            "tts_latency_ms": self.metrics.tts_latency,
            "total_latency_ms": self.metrics.total_latency,
            "frames_processed": self.metrics.frames_processed,
            "errors": self.metrics.errors,
            "component_timings": self.metrics.component_timings.copy()
        }
        
        # Emit as system frame
        # Use TextFrame to carry metrics data
        metrics_json = json.dumps({"type": "metrics_update", "data": metrics_data})
        await self.push_frame(TextFrame(metrics_json))
        
        # Call event callback if provided
        if self.event_callback:
            self.event_callback("metrics", metrics_data)
            
        logger.info(f"Metrics: {metrics_data}")
