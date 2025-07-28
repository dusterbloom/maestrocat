# core/processors/metrics_aggregator.py
"""Turn-based Metrics Aggregator for Voice Agent Performance

Measures proper turn-based latencies:
1. STT Latency: User speaking start → transcription complete
2. LLM Latency: Transcription complete → first LLM token
3. TTS Latency: First LLM token → first TTS audio
"""

import asyncio
import time
import logging
from typing import Optional, Dict, Any

from pipecat.frames.frames import Frame
from pipecat.processors.frame_processor import FrameProcessor

logger = logging.getLogger(__name__)


class MetricsAggregatorProcessor(FrameProcessor):
    """
    Aggregates turn-based metrics for voice agents.
    
    Tracks the complete user turn lifecycle:
    - User starts speaking
    - STT produces transcription 
    - LLM produces first token
    - TTS produces first audio
    """
    
    def __init__(self, event_emitter=None, **kwargs):
        super().__init__(**kwargs)
        self._event_emitter = event_emitter
        
        # Turn state tracking
        self._turn_start_time: Optional[float] = None
        self._transcription_complete_time: Optional[float] = None
        self._llm_first_token_time: Optional[float] = None
        self._tts_audio_start_time: Optional[float] = None
        
        # Current turn metrics
        self._current_turn: Dict[str, float] = {
            "stt_latency_ms": 0.0,
            "llm_latency_ms": 0.0, 
            "tts_latency_ms": 0.0,
            "total_latency_ms": 0.0
        }
        
        # Subscribe to relevant events
        if self._event_emitter:
            self._setup_event_subscriptions()
            
    def _setup_event_subscriptions(self):
        """Subscribe to pipeline events for turn tracking"""
        
        async def on_turn_started(turn_number):
            """Turn started - begin new turn metrics tracking"""
            self._turn_start_time = time.time()
            self._transcription_complete_time = None
            self._llm_first_token_time = None
            self._tts_audio_start_time = None
            self._current_turn = {
                "stt_latency_ms": 0.0,
                "llm_latency_ms": 0.0,
                "tts_latency_ms": 0.0,
                "total_latency_ms": 0.0
            }
            logger.debug(f"📊 Turn {turn_number} started - metrics tracking begin")
        
        async def on_transcription_complete(data):
            """STT completed - measure STT latency"""
            if self._turn_start_time:
                self._transcription_complete_time = time.time()
                stt_latency = (self._transcription_complete_time - self._turn_start_time) * 1000
                self._current_turn["stt_latency_ms"] = stt_latency
                logger.debug(f"📊 STT completed: {stt_latency:.1f}ms")
                
        async def on_llm_first_token(data):
            """LLM first token - measure LLM latency"""
            if self._transcription_complete_time:
                self._llm_first_token_time = time.time()
                llm_latency = (self._llm_first_token_time - self._transcription_complete_time) * 1000
                self._current_turn["llm_latency_ms"] = llm_latency
                logger.debug(f"📊 LLM first token: {llm_latency:.1f}ms")
                
        async def on_tts_audio_start(data):
            """TTS audio started - measure TTS latency and complete turn"""
            if self._llm_first_token_time:
                self._tts_audio_start_time = time.time()
                tts_latency = (self._tts_audio_start_time - self._llm_first_token_time) * 1000
                self._current_turn["tts_latency_ms"] = tts_latency
                
                # Calculate total turn latency
                if self._turn_start_time:
                    total_latency = (self._tts_audio_start_time - self._turn_start_time) * 1000
                    self._current_turn["total_latency_ms"] = total_latency
                    
                    # Emit complete turn metrics
                    await self._emit_turn_metrics()
                    logger.info(f"📊 Turn completed - STT: {self._current_turn['stt_latency_ms']:.1f}ms, "
                              f"LLM: {self._current_turn['llm_latency_ms']:.1f}ms, "
                              f"TTS: {self._current_turn['tts_latency_ms']:.1f}ms, "
                              f"Total: {self._current_turn['total_latency_ms']:.1f}ms")
        
        # Subscribe to events using the correct API
        self._event_emitter.subscribe("turn_started", on_turn_started)
        self._event_emitter.subscribe("transcription_final", on_transcription_complete)
        self._event_emitter.subscribe("llm_response_start", on_llm_first_token)
        self._event_emitter.subscribe("tts_audio_start", on_tts_audio_start)
                    
    async def _emit_turn_metrics(self):
        """Emit aggregated turn metrics"""
        if self._event_emitter:
            metrics = {
                **self._current_turn,
                "timestamp": time.time(),
                "component": "turn_aggregator"
            }
            
            await self._event_emitter.emit("metrics_update", metrics)
            
    async def process_frame(self, frame: Frame, direction):
        """Process frames (pass-through)"""
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        
    def get_current_metrics(self) -> Dict[str, float]:
        """Get current turn metrics"""
        return self._current_turn.copy()
        
    def reset_turn(self):
        """Reset turn tracking (for testing/debugging)"""
        self._turn_start_time = None
        self._transcription_complete_time = None
        self._llm_first_token_time = None
        self._tts_audio_start_time = None
        self._current_turn = {
            "stt_latency_ms": 0.0,
            "llm_latency_ms": 0.0,
            "tts_latency_ms": 0.0, 
            "total_latency_ms": 0.0
        }