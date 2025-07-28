# core/processors/turn_metrics_tracker.py
"""
Turn-Based Metrics Tracker for Voice Agent Performance

This is a SAFE, ADDITIVE metrics system that tracks conversation turns
without modifying existing metrics or breaking the pipeline.

Emits new event type: 'turn_metrics' for per-conversation-turn timing.
"""

import time
import logging
from typing import Optional, Dict, Any

from pipecat.frames.frames import Frame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame
from pipecat.processors.frame_processor import FrameProcessor

logger = logging.getLogger(__name__)


class TurnMetricsTracker(FrameProcessor):
    """
    Safe, additive turn-based metrics tracker.
    
    Tracks conversation turns from user speaking to first audio response:
    1. User starts speaking → Mark turn start
    2. User stops speaking → STT processing begins  
    3. Transcription complete → LLM processing begins
    4. LLM first token → TTS processing begins
    5. TTS first audio → Turn complete
    
    Emits 'turn_metrics' events (separate from existing 'metrics_update')
    """
    
    def __init__(self, event_emitter=None, **kwargs):
        super().__init__(**kwargs)
        self._event_emitter = event_emitter
        
        # Turn state tracking
        self._current_turn = None
        self._turn_counter = 0
        
        # Subscribe to pipeline events if event emitter available
        if self._event_emitter:
            self._setup_event_subscriptions()
            
    def _setup_event_subscriptions(self):
        """Subscribe to pipeline events for turn tracking"""
        
        async def on_transcription_final(data):
            """STT completed - record transcription time"""
            if self._current_turn and "user_stopped_time" in self._current_turn:
                now = time.time()
                self._current_turn["transcription_complete_time"] = now
                stt_latency = (now - self._current_turn["user_stopped_time"]) * 1000
                self._current_turn["stt_latency_ms"] = round(stt_latency, 1)
                logger.debug(f"📊 Turn {self._current_turn['turn_id']}: STT completed in {stt_latency:.1f}ms")
        
        async def on_transcription_complete(data):
            """Alternative STT event name - same logic"""
            await on_transcription_final(data)
                
        async def on_llm_first_token(data):
            """LLM first token received - record actual LLM processing time"""
            if self._current_turn and "transcription_complete_time" in self._current_turn:
                now = time.time()
                self._current_turn["llm_first_token_time"] = now
                llm_latency = (now - self._current_turn["transcription_complete_time"]) * 1000
                self._current_turn["llm_latency_ms"] = round(llm_latency, 1)
                logger.debug(f"📊 Turn {self._current_turn['turn_id']}: LLM first token in {llm_latency:.1f}ms")
                
        async def on_tts_audio_start(data):
            """TTS audio started - complete turn metrics"""
            if self._current_turn and "llm_first_token_time" in self._current_turn:
                now = time.time()
                self._current_turn["tts_audio_start_time"] = now
                tts_latency = (now - self._current_turn["llm_first_token_time"]) * 1000
                self._current_turn["tts_latency_ms"] = round(tts_latency, 1)
                
                # Calculate total turn latency (user stopped speaking → first audio)
                if "user_stopped_time" in self._current_turn:
                    total_latency = (now - self._current_turn["user_stopped_time"]) * 1000
                    self._current_turn["total_latency_ms"] = round(total_latency, 1)
                    
                    # Verify math adds up (with rounding tolerance)
                    calculated_total = (self._current_turn.get("stt_latency_ms", 0) + 
                                      self._current_turn.get("llm_latency_ms", 0) + 
                                      self._current_turn.get("tts_latency_ms", 0))
                    math_diff = abs(calculated_total - self._current_turn["total_latency_ms"])
                    if math_diff > 2.0:  # Allow 2ms tolerance for rounding
                        logger.warning(f"📊 Turn {self._current_turn['turn_id']}: Math mismatch - "
                                     f"Sum: {calculated_total:.1f}ms vs Total: {self._current_turn['total_latency_ms']:.1f}ms "
                                     f"(diff: {math_diff:.1f}ms)")
                    
                    # Emit complete turn metrics
                    await self._emit_turn_metrics()
                    
                    logger.info(f"📊 Turn {self._current_turn['turn_id']} completed - "
                              f"STT: {self._current_turn.get('stt_latency_ms', 0):.1f}ms, "
                              f"LLM: {self._current_turn.get('llm_latency_ms', 0):.1f}ms, "
                              f"TTS: {self._current_turn.get('tts_latency_ms', 0):.1f}ms, "
                              f"Total: {self._current_turn.get('total_latency_ms', 0):.1f}ms")
                    
                    # Reset for next turn
                    self._current_turn = None
        
        # Subscribe to events - handle both event naming conventions
        try:
            self._event_emitter.subscribe("transcription_final", on_transcription_final)
            self._event_emitter.subscribe("transcription_complete", on_transcription_complete)
            self._event_emitter.subscribe("llm_first_token", on_llm_first_token)  # Subscribe to actual first token event
            self._event_emitter.subscribe("llm_response_start", on_llm_first_token)  # Fallback for existing event
            self._event_emitter.subscribe("tts_audio_start", on_tts_audio_start)
            logger.info("📊 TurnMetricsTracker: Successfully subscribed to pipeline events")
        except Exception as e:
            logger.warning(f"📊 TurnMetricsTracker: Failed to subscribe to events: {e}")
            
    async def process_frame(self, frame: Frame, direction):
        """Process frames to detect turn boundaries"""
        await super().process_frame(frame, direction)
        
        # Detect user speaking frames
        if isinstance(frame, UserStartedSpeakingFrame):
            await self._handle_user_started_speaking()
        elif isinstance(frame, UserStoppedSpeakingFrame):
            await self._handle_user_stopped_speaking()
        
        # Pass frame through unchanged
        await self.push_frame(frame, direction)
        
    async def _handle_user_started_speaking(self):
        """User started speaking - prepare for new turn"""
        # Cancel any incomplete turn (user interrupted themselves)
        if self._current_turn:
            logger.debug(f"📊 Turn {self._current_turn['turn_id']}: Cancelled due to new user speech")
            
        # Start new turn tracking
        self._turn_counter += 1
        self._current_turn = {
            "turn_id": self._turn_counter,
            "user_started_time": time.time(),
            "stt_latency_ms": 0.0,
            "llm_latency_ms": 0.0,
            "tts_latency_ms": 0.0,
            "total_latency_ms": 0.0
        }
        logger.debug(f"📊 Turn {self._turn_counter}: User started speaking")
        
    async def _handle_user_stopped_speaking(self):
        """User stopped speaking - STT processing begins"""
        if self._current_turn:
            self._current_turn["user_stopped_time"] = time.time()
            speaking_duration = (self._current_turn["user_stopped_time"] - 
                               self._current_turn["user_started_time"]) * 1000
            self._current_turn["speaking_duration_ms"] = speaking_duration
            logger.debug(f"📊 Turn {self._current_turn['turn_id']}: User stopped speaking "
                        f"(spoke for {speaking_duration:.1f}ms)")
                        
    async def _emit_turn_metrics(self):
        """Emit complete turn metrics as new event type"""
        if self._event_emitter and self._current_turn:
            # Round all values consistently
            stt_ms = round(self._current_turn.get("stt_latency_ms", 0.0), 1)
            llm_ms = round(self._current_turn.get("llm_latency_ms", 0.0), 1)
            tts_ms = round(self._current_turn.get("tts_latency_ms", 0.0), 1)
            total_ms = round(self._current_turn.get("total_latency_ms", 0.0), 1)
            
            turn_metrics = {
                "turn_id": self._current_turn["turn_id"],
                "stt_latency_ms": stt_ms,
                "llm_latency_ms": llm_ms,
                "tts_latency_ms": tts_ms,
                "total_latency_ms": total_ms,
                "speaking_duration_ms": round(self._current_turn.get("speaking_duration_ms", 0.0), 1),
                "timestamp": time.time(),
                "component": "turn_tracker",
                # Add math check for debugging
                "math_check": {
                    "sum": stt_ms + llm_ms + tts_ms,
                    "total": total_ms,
                    "diff": round(abs((stt_ms + llm_ms + tts_ms) - total_ms), 1)
                }
            }
            
            # Emit as NEW event type to avoid conflicts
            await self._event_emitter.emit("turn_metrics", turn_metrics)
            
    def get_current_turn(self) -> Optional[Dict[str, Any]]:
        """Get current turn data (for debugging)"""
        return self._current_turn.copy() if self._current_turn else None
        
    def get_turn_counter(self) -> int:
        """Get current turn number"""
        return self._turn_counter
        
    def reset(self):
        """Reset tracker state (for testing)"""
        self._current_turn = None
        self._turn_counter = 0
        logger.info("📊 TurnMetricsTracker: Reset")