# Enhanced WhisperLive STT Service with Reliability Framework
"""
WhisperLive STT Service enhanced with comprehensive error recovery capabilities.
Includes circuit breaker protection, exponential backoff, health monitoring, and graceful degradation.
"""

import asyncio
import json
import time
import numpy as np
from typing import AsyncGenerator, Optional, Dict, Any
import websockets
import logging

from pipecat.frames.frames import Frame, AudioRawFrame, InputAudioRawFrame, UserAudioRawFrame, TranscriptionFrame, SystemFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame
from pipecat.services.stt_service import STTService
from pipecat.processors.frame_processor import FrameDirection

# Import reliability framework
from ..reliability import (
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenError,
    ExponentialBackoff, BackoffConfig, BackoffStrategy,
    ErrorHandler, ErrorLevel, RecoveryStrategy,
    MemoryGuard, MemoryThreshold,
    is_network_error
)

logger = logging.getLogger(__name__)


class ReliableWhisperLiveSTTService(STTService):
    """
    Enhanced WhisperLive STT Service with comprehensive reliability features.
    
    Features:
    - Circuit breaker protection against service failures
    - Exponential backoff for reconnection attempts
    - Health monitoring and automatic recovery
    - Memory leak prevention
    - Graceful degradation with fallback strategies
    - Comprehensive error handling and recovery
    """
    
    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 9090,
        language: str = "en",
        translate: bool = False,
        model: str = "small",
        use_vad: bool = True,
        vad_threshold: float = 0.3,
        event_emitter = None,
        service_registry = None,
        
        # Reliability configuration
        enable_circuit_breaker: bool = True,
        enable_health_monitoring: bool = True,
        enable_memory_guard: bool = True,
        fallback_to_silence: bool = True,
        
        **kwargs
    ):
        super().__init__(**kwargs)
        
        # Service configuration
        self._host = host
        self._port = port
        self._language = language
        self._translate = translate
        self._model = model
        self._use_vad = use_vad
        self._vad_threshold = vad_threshold
        self._event_emitter = event_emitter
        self._service_registry = service_registry
        
        # Connection state
        self._websocket = None
        self._receive_task = None
        self._client_uid = None
        self._connection_healthy = False
        
        # Audio processing
        self._audio_buffer = bytearray()
        self._processed_segments = set()
        self._max_segments = 100
        
        # Reliability components
        self._setup_reliability_components(
            enable_circuit_breaker,
            enable_health_monitoring,
            enable_memory_guard,
            fallback_to_silence
        )
        
    def _setup_reliability_components(
        self,
        enable_circuit_breaker: bool,
        enable_health_monitoring: bool,
        enable_memory_guard: bool,
        fallback_to_silence: bool
    ):
        """Initialize reliability framework components"""
        service_name = f"whisperlive_stt_{self._host}_{self._port}"
        
        # Circuit breaker
        if enable_circuit_breaker:
            circuit_config = CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout=30.0,
                request_timeout=10.0,
                health_check_interval=15.0
            )
            self._circuit_breaker = CircuitBreaker(
                name=service_name,
                config=circuit_config,
                event_emitter=self._event_emitter
            )
            self._circuit_breaker.set_health_check(self._health_check)
        else:
            self._circuit_breaker = None
            
        # Exponential backoff for reconnections
        backoff_config = BackoffConfig(
            initial_delay=1.0,
            max_delay=60.0,
            multiplier=2.0,
            jitter=True,
            max_retries=5,
            strategy=BackoffStrategy.EXPONENTIAL
        )
        self._backoff = ExponentialBackoff(
            name=f"{service_name}_reconnect",
            config=backoff_config,
            event_emitter=self._event_emitter
        )
        
        # Error handler
        self._error_handler = ErrorHandler(
            service_name=service_name,
            event_emitter=self._event_emitter,
            circuit_breaker=self._circuit_breaker,
            service_registry=self._service_registry
        )
        
        # Register custom error patterns
        self._register_error_patterns()
        
        # Memory guard
        if enable_memory_guard:
            self._memory_guard = MemoryGuard(
                service_name=service_name,
                event_emitter=self._event_emitter,
                medium_threshold_mb=256,
                high_threshold_mb=512,
                critical_threshold_mb=1024
            )
            
            # Register managed buffers
            self._memory_guard.register_managed_buffer(
                "audio_buffer", self._audio_buffer, max_size=32768
            )
            self._memory_guard.register_managed_buffer(
                "processed_segments", list(self._processed_segments), max_size=self._max_segments
            )
        else:
            self._memory_guard = None
            
        # Fallback configuration
        self._fallback_to_silence = fallback_to_silence
        
    def _register_error_patterns(self):
        """Register service-specific error patterns"""
        from ..reliability.error_handler import ErrorPattern
        
        # WebSocket connection errors
        self._error_handler.register_error_pattern(ErrorPattern(
            exception_type="ConnectionClosedError",
            level=ErrorLevel.WARNING,
            strategy=RecoveryStrategy.RETRY,
            max_occurrences=3,
            metadata={"escalate_to": RecoveryStrategy.CIRCUIT_BREAK}
        ))
        
        # WhisperLive server errors
        self._error_handler.register_error_pattern(ErrorPattern(
            exception_type="WebSocketException",
            level=ErrorLevel.ERROR,
            strategy=RecoveryStrategy.FAILOVER,
            max_occurrences=2
        ))
        
        # JSON decode errors (malformed responses)
        self._error_handler.register_error_pattern(ErrorPattern(
            exception_type="JSONDecodeError",
            level=ErrorLevel.WARNING,
            strategy=RecoveryStrategy.IGNORE,
            max_occurrences=10
        ))
        
    async def start(self, frame: SystemFrame):
        """Start the enhanced STT service"""
        await super().start(frame)
        
        # Start reliability components
        if self._memory_guard:
            await self._memory_guard.start()
            
        # Connect with reliability protection
        await self._reliable_connect()
        
    async def stop(self):
        """Stop the enhanced STT service"""
        await super().stop()
        
        # Clean shutdown
        await self._graceful_disconnect()
        
        # Stop reliability components
        if self._memory_guard:
            await self._memory_guard.stop()
            
        if self._circuit_breaker:
            await self._circuit_breaker.close()
            
    async def _reliable_connect(self):
        """Connect with circuit breaker and retry logic"""
        try:
            if self._circuit_breaker:
                await self._circuit_breaker.call(self._connect_internal)
            else:
                await self._connect_internal()
                
        except CircuitBreakerOpenError:
            logger.warning("Circuit breaker is open, using fallback strategy")
            await self._handle_service_unavailable()
            
        except Exception as e:
            recovery_strategy = await self._error_handler.handle_error(
                e, {"operation": "connect"}, "connection"
            )
            
            if recovery_strategy == RecoveryStrategy.RETRY:
                await self._retry_connect()
            elif recovery_strategy == RecoveryStrategy.FAILOVER:
                await self._handle_service_unavailable()
            else:
                raise
                
    async def _connect_internal(self):
        """Internal connection logic"""
        url = f"ws://{self._host}:{self._port}"
        
        # Connect with timeout
        self._websocket = await asyncio.wait_for(
            websockets.connect(url),
            timeout=10.0
        )
        
        # Send configuration
        self._client_uid = f"pipecat_{int(time.time() * 1000)}"
        config = {
            "uid": self._client_uid,
            "language": self._language,
            "task": "translate" if self._translate else "transcribe",
            "model": self._model,
            "use_vad": self._use_vad,
            "max_clients": 4,
            "max_connection_time": 600,
            "send_last_n_segments": 10,
            "no_speech_thresh": 0.45,
            "clip_audio": False,
            "same_output_threshold": 10
        }
        
        await self._websocket.send(json.dumps(config))
        logger.info(f"Connected to WhisperLive at {url}")
        
        # Start receive task
        self._receive_task = asyncio.create_task(self._reliable_receive_loop())
        self._connection_healthy = True
        
    async def _retry_connect(self):
        """Retry connection with exponential backoff"""
        try:
            await self._backoff.execute(
                self._connect_internal,
                is_retriable=is_network_error
            )
        except Exception as e:
            logger.error(f"Failed to reconnect after retries: {e}")
            await self._handle_service_unavailable()
            
    async def _reliable_receive_loop(self):
        """Enhanced receive loop with error handling"""
        while self._websocket and self._connection_healthy:
            try:
                # Use circuit breaker for receive operations
                if self._circuit_breaker:
                    message = await self._circuit_breaker.call(
                        self._receive_message_with_timeout
                    )
                else:
                    message = await self._receive_message_with_timeout()
                    
                await self._process_message(message)
                
            except CircuitBreakerOpenError:
                logger.warning("Circuit breaker open during receive")
                await self._handle_connection_failure()
                break
                
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WhisperLive connection closed")
                await self._handle_connection_failure()
                break
                
            except Exception as e:
                recovery_strategy = await self._error_handler.handle_error(
                    e, {"operation": "receive"}, "receive_loop"
                )
                
                if recovery_strategy in (RecoveryStrategy.CIRCUIT_BREAK, RecoveryStrategy.FAILOVER):
                    await self._handle_connection_failure()
                    break
                elif recovery_strategy == RecoveryStrategy.IGNORE:
                    continue
                else:
                    logger.error(f"Unhandled error in receive loop: {e}")
                    break
                    
    async def _receive_message_with_timeout(self) -> str:
        """Receive message with timeout"""
        return await asyncio.wait_for(
            self._websocket.recv(),
            timeout=30.0
        )
        
    async def _process_message(self, message):
        """Process received message with error handling"""
        try:
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    # Handle as plain text transcription
                    await self._handle_transcription(message, is_final=True)
                    
            elif isinstance(message, bytes):
                logger.debug(f"Received binary message: {len(message)} bytes")
                
        except Exception as e:
            await self._error_handler.handle_error(
                e, {"message_type": type(message).__name__}, "message_processing"
            )
            
    async def _handle_message(self, data: Dict[str, Any]):
        """Enhanced message handling with validation"""
        try:
            # Validate message structure
            if not isinstance(data, dict):
                logger.warning(f"Invalid message format: {type(data)}")
                return
                
            # Check if message is for our client
            if "uid" in data and data["uid"] != self._client_uid:
                return
                
            # Handle segments (main transcription format)
            if "segments" in data:
                segments = data["segments"]
                
                for segment in segments:
                    text = segment.get("text", "").strip()
                    completed = segment.get("completed", False)
                    start = segment.get("start", "")
                    end = segment.get("end", "")
                    
                    # Create unique segment identifier
                    segment_id = f"{start}-{end}-{text}"
                    
                    if text and completed and segment_id not in self._processed_segments:
                        # Memory management
                        if len(self._processed_segments) > self._max_segments:
                            # Remove oldest segments
                            oldest_segments = list(self._processed_segments)[:50]
                            for old_id in oldest_segments:
                                self._processed_segments.discard(old_id)
                                
                        self._processed_segments.add(segment_id)
                        await self._handle_transcription(text, is_final=True)
                        
            # Handle other message types
            elif "message" in data:
                message = data.get("message", "")
                if message == "SERVER_READY":
                    logger.info("WhisperLive server is ready")
                elif message in ["ERROR", "WARNING"]:
                    logger.warning(f"WhisperLive server message: {message}")
                    
        except Exception as e:
            await self._error_handler.handle_error(
                e, {"data": data}, "message_handling"
            )
            
    async def _handle_transcription(self, text: str, is_final: bool):
        """Enhanced transcription handling with filtering"""
        if not text:
            return
            
        try:
            # Filter hallucinations
            if self._is_hallucination(text):
                logger.debug(f"Filtered hallucination: '{text}'")
                return
                
            # Create transcription frame
            frame = TranscriptionFrame(
                text=text,
                user_id="user",
                timestamp=time.time()
            )
            
            await self.push_frame(frame)
            
            if is_final:
                logger.info(f"Transcription: '{text}'")
                
                # Emit event
                if self._event_emitter:
                    await self._event_emitter.emit("transcription_complete", {
                        "text": text,
                        "service": "whisperlive",
                        "confidence": 1.0,
                        "timestamp": time.time()
                    })
                    
        except Exception as e:
            await self._error_handler.handle_error(
                e, {"text": text, "is_final": is_final}, "transcription_handling"
            )
            
    def _is_hallucination(self, text: str) -> bool:
        """Check if text is likely a hallucination"""
        hallucination_phrases = [
            "thanks for watching",
            "see you in the next video",
            "don't forget to subscribe",
            "like and subscribe",
            "thank you for watching",
            "see you next time",
            "music playing",
            "applause",
            "laughter",
            "subtitle by",
            "captions by"
        ]
        
        text_lower = text.lower().strip()
        return any(phrase in text_lower for phrase in hallucination_phrases)
        
    async def _handle_connection_failure(self):
        """Handle connection failures with recovery"""
        self._connection_healthy = False
        
        if self._receive_task:
            self._receive_task.cancel()
            
        # Attempt reconnection
        logger.info("Attempting to reconnect to WhisperLive")
        
        try:
            await self._retry_connect()
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            await self._handle_service_unavailable()
            
    async def _handle_service_unavailable(self):
        """Handle complete service unavailability"""
        logger.warning("WhisperLive service unavailable, using fallback strategy")
        
        if self._fallback_to_silence:
            # Continue processing but don't generate transcriptions
            logger.info("Falling back to silent operation")
        else:
            # Emit service unavailable event
            if self._event_emitter:
                await self._event_emitter.emit("service_unavailable", {
                    "service": "whisperlive_stt",
                    "timestamp": time.time()
                })
                
    async def _health_check(self) -> bool:
        """Health check for circuit breaker"""
        try:
            if not self._websocket or self._websocket.closed:
                return False
                
            # Send ping to check connection
            await asyncio.wait_for(self._websocket.ping(), timeout=5.0)
            return True
            
        except Exception:
            return False
            
    async def _graceful_disconnect(self):
        """Gracefully disconnect from service"""
        self._connection_healthy = False
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
                
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as e:
                logger.debug(f"Error closing websocket: {e}")
            finally:
                self._websocket = None
                
    async def process_frame(self, frame: Frame, direction):
        """Enhanced frame processing with reliability protection"""
        try:
            await super().process_frame(frame, direction)
            
            # Handle audio frames
            if isinstance(frame, (AudioRawFrame, InputAudioRawFrame, UserAudioRawFrame)):
                if self._connection_healthy and self._websocket:
                    await self._process_audio_frame(frame)
                    
            await self.push_frame(frame, direction)
            
        except Exception as e:
            recovery_strategy = await self._error_handler.handle_error(
                e, {"frame_type": type(frame).__name__}, "frame_processing"
            )
            
            if recovery_strategy != RecoveryStrategy.IGNORE:
                # Still push the frame to avoid breaking the pipeline
                await self.push_frame(frame, direction)
                
    async def _process_audio_frame(self, frame):
        """Process audio frame with circuit breaker protection"""
        try:
            # Check audio amplitude to avoid processing silence
            audio_samples = np.frombuffer(frame.audio, dtype=np.int16)
            max_amplitude = np.max(np.abs(audio_samples)) if len(audio_samples) > 0 else 0
            
            if max_amplitude > 2000:  # Threshold for meaningful audio
                self._audio_buffer.extend(frame.audio)
                
                # Send audio chunks
                chunk_size = 16384
                while len(self._audio_buffer) >= chunk_size:
                    chunk_data = self._audio_buffer[:chunk_size]
                    self._audio_buffer = self._audio_buffer[chunk_size:]
                    
                    # Convert and send
                    audio_samples_int16 = np.frombuffer(chunk_data, dtype=np.int16)
                    audio_samples_float32 = audio_samples_int16.astype(np.float32) / 32768.0
                    chunk = audio_samples_float32.tobytes()
                    
                    if self._circuit_breaker:
                        await self._circuit_breaker.call(self._send_audio_chunk, chunk)
                    else:
                        await self._send_audio_chunk(chunk)
                        
        except CircuitBreakerOpenError:
            # Circuit breaker is open, skip audio processing
            logger.debug("Skipping audio processing - circuit breaker open")
            
        except Exception as e:
            await self._error_handler.handle_error(
                e, {"audio_length": len(frame.audio)}, "audio_processing"
            )
            
    async def _send_audio_chunk(self, chunk: bytes):
        """Send audio chunk with timeout"""
        if self._websocket and not self._websocket.closed:
            await asyncio.wait_for(
                self._websocket.send(chunk),
                timeout=5.0
            )
            
    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Enhanced STT processing"""
        # This method is required by STTService but we handle audio in process_frame
        yield  # Make this an async generator
        
    def get_reliability_stats(self) -> Dict[str, Any]:
        """Get comprehensive reliability statistics"""
        stats = {
            "service_name": "whisperlive_stt",
            "connection_healthy": self._connection_healthy,
            "processed_segments": len(self._processed_segments),
            "audio_buffer_size": len(self._audio_buffer)
        }
        
        if self._circuit_breaker:
            stats["circuit_breaker"] = self._circuit_breaker.get_stats()
            
        if self._memory_guard:
            stats["memory"] = self._memory_guard.get_memory_stats()
            
        if self._error_handler:
            stats["errors"] = self._error_handler.get_error_stats()
            
        stats["backoff"] = self._backoff.get_stats()
        
        return stats