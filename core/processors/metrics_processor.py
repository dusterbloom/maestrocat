# core/processors/metrics_processor.py
"""
Unified Metrics Processor for Voice Agent Performance
"""

import time
import logging
from typing import Optional, Dict, Any

from pipecat.frames.frames import Frame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame
from pipecat.processors.frame_processor import FrameProcessor

logger = logging.getLogger(__name__)


class MetricsProcessor(FrameProcessor):
    """
    A unified processor that tracks and emits all key performance metrics for a voice agent turn.
    """
    
    def __init__(self, event_emitter=None, **kwargs):
        super().__init__(**kwargs)
        self._event_emitter = event_emitter
        self._current_turn = None
        self._turn_counter = 0
        
        if self._event_emitter:
            self._setup_event_subscriptions()
            
    def _setup_event_subscriptions(self):
        """Subscribe to all necessary pipeline events for comprehensive metrics."""
        subscriptions = {
            "transcription_final": self._on_transcription_final,
            "llm_response_start": self._on_llm_first_token,
            "tts_audio_start": self._on_tts_audio_start,
        }
        for event, handler in subscriptions.items():
            self._event_emitter.subscribe(event, handler)
        logger.info("📊 MetricsProcessor: Subscribed to all performance events.")

    async def process_frame(self, frame: Frame, direction):
        """Process frames to detect turn boundaries."""
        await super().process_frame(frame, direction)
        
        if isinstance(frame, UserStartedSpeakingFrame):
            await self._handle_user_started_speaking()
        elif isinstance(frame, UserStoppedSpeakingFrame):
            await self._handle_user_stopped_speaking()
        
        await self.push_frame(frame, direction)
        
    async def _handle_user_started_speaking(self):
        """User started speaking - prepare for new turn."""
        if self._current_turn:
            logger.debug(f"📊 Turn {self._current_turn['turn_id']} interrupted.")
            
        self._turn_counter += 1
        self._current_turn = {
            "turn_id": self._turn_counter,
            "user_started_time": time.time(),
        }
        logger.debug(f"📊 Turn {self._turn_counter} started.")
        
    async def _handle_user_stopped_speaking(self):
        """User stopped speaking - mark the time."""
        if self._current_turn:
            self._current_turn["user_stopped_time"] = time.time()
            duration = (self._current_turn["user_stopped_time"] - self._current_turn["user_started_time"]) * 1000
            self._current_turn["speaking_duration_ms"] = duration
            logger.debug(f"📊 Turn {self._current_turn['turn_id']} user spoke for {duration:.1f}ms.")

    async def _on_transcription_final(self, data):
        """STT completed - calculate STT latency."""
        if self._current_turn and "user_stopped_time" in self._current_turn:
            now = time.time()
            self._current_turn["transcription_complete_time"] = now
            latency = (now - self._current_turn["user_stopped_time"]) * 1000
            self._current_turn["stt_latency_ms"] = latency
            logger.debug(f"📊 Turn {self._current_turn['turn_id']}: STT latency {latency:.1f}ms")

    async def _on_llm_first_token(self, data):
        """LLM first token received - calculate LLM latency."""
        if self._current_turn and "transcription_complete_time" in self._current_turn:
            now = time.time()
            self._current_turn["llm_first_token_time"] = now
            latency = (now - self._current_turn["transcription_complete_time"]) * 1000
            self._current_turn["llm_latency_ms"] = latency
            logger.debug(f"📊 Turn {self._current_turn['turn_id']}: LLM latency {latency:.1f}ms")

    async def _on_tts_audio_start(self, data):
        """TTS audio started - calculate TTS latency and finalize the turn."""
        if self._current_turn and "llm_first_token_time" in self._current_turn:
            now = time.time()
            self._current_turn["tts_audio_start_time"] = now
            tts_latency = (now - self._current_turn["llm_first_token_time"]) * 1000
            self._current_turn["tts_latency_ms"] = tts_latency
            
            total_latency = (now - self._current_turn["user_stopped_time"]) * 1000
            self._current_turn["total_latency_ms"] = total_latency
            
            logger.info(f"📊 Turn {self._current_turn['turn_id']} complete. Total latency: {total_latency:.1f}ms")
            await self._emit_metrics()
            self._current_turn = None

    async def _emit_metrics(self):
        """Emit the consolidated metrics for the completed turn."""
        if self._event_emitter and self._current_turn:
            # Create the metrics payload
            metrics = {
                "stt_latency_ms": self._current_turn.get("stt_latency_ms", 0),
                "llm_latency_ms": self._current_turn.get("llm_latency_ms", 0),
                "tts_latency_ms": self._current_turn.get("tts_latency_ms", 0),
                "total_latency_ms": self._current_turn.get("total_latency_ms", 0),
                "speaking_duration_ms": self._current_turn.get("speaking_duration_ms", 0),
                "timestamp": time.time(),
            }
            
            # Emit the generic metrics update for the component cards
            await self._event_emitter.emit("metrics_update", metrics)

            # Also emit the specific turn_metrics event for the developer display
            turn_data = {**metrics, "turn_id": self._current_turn.get("turn_id", 0)}
            await self._event_emitter.emit("turn_metrics", turn_data)