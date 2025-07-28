# Enhanced Kokoro TTS Service with Reliability Framework
"""
Kokoro TTS Service enhanced with comprehensive error recovery capabilities.
Includes circuit breaker protection, HTTP health monitoring, and graceful degradation.
"""

import httpx
import time
import asyncio
import numpy as np
from typing import AsyncGenerator, Optional, Dict, Any
import logging
import io
import wave

from pipecat.frames.frames import Frame, TTSAudioRawFrame, SystemFrame, TextFrame
from pipecat.services.tts_service import TTSService
from pipecat.processors.frame_processor import FrameDirection

# Import reliability framework
from ..reliability import (
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenError,
    ExponentialBackoff, BackoffConfig, BackoffStrategy,
    ErrorHandler, ErrorLevel, RecoveryStrategy,
    MemoryGuard, MemoryThreshold,
    is_network_error, is_service_unavailable_error
)

logger = logging.getLogger(__name__)


class ReliableKokoroTTSService(TTSService):
    """
    Enhanced Kokoro TTS Service with comprehensive reliability features.
    
    Features:
    - Circuit breaker protection against HTTP service failures
    - Exponential backoff for request retries
    - Health monitoring with automatic recovery
    - Memory management for streaming buffers
    - Graceful degradation with fallback TTS
    - Request timeout and cancellation handling
    """
    
    def __init__(
        self,
        *,
        base_url: str = "http://localhost:5000",
        voice: str = "af_bella",
        speed: float = 1.0,
        sample_rate: int = 24000,
        event_emitter = None,
        service_registry = None,
        
        # Reliability configuration
        enable_circuit_breaker: bool = True,
        enable_health_monitoring: bool = True,
        enable_memory_guard: bool = True,
        fallback_tts = None,
        
        # HTTP configuration
        max_retries: int = 2,
        request_timeout: float = 30.0,
        connection_timeout: float = 5.0,
        
        **kwargs
    ):
        super().__init__(
            aggregate_sentences=True,
            **kwargs
        )
        
        # Service configuration
        self._base_url = base_url
        self._voice = voice
        self._speed = speed
        self._sample_rate = sample_rate
        self._event_emitter = event_emitter
        self._service_registry = service_registry
        
        # HTTP client configuration
        self._request_timeout = request_timeout
        self._connection_timeout = connection_timeout
        
        # Streaming state
        self._current_request = None
        self._audio_buffer = b""
        self._streaming_buffer = []
        self._buffer_samples = int(self._sample_rate * 0.005)
        
        # Fallback TTS
        self._fallback_tts = fallback_tts
        self._using_fallback = False
        
        # Reliability components
        self._setup_reliability_components(
            enable_circuit_breaker,
            enable_health_monitoring,
            enable_memory_guard,
            max_retries
        )
        
        # HTTP client with reliability features
        self._setup_http_client()
        
    def _setup_reliability_components(
        self,
        enable_circuit_breaker: bool,
        enable_health_monitoring: bool,
        enable_memory_guard: bool,
        max_retries: int
    ):
        """Initialize reliability framework components"""
        service_name = f"kokoro_tts_{self._base_url.replace('://', '_').replace(':', '_')}"
        
        # Circuit breaker
        if enable_circuit_breaker:
            circuit_config = CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout=60.0,  # Longer timeout for TTS recovery
                request_timeout=self._request_timeout,
                health_check_interval=30.0
            )
            self._circuit_breaker = CircuitBreaker(
                name=service_name,
                config=circuit_config,
                event_emitter=self._event_emitter
            )
            self._circuit_breaker.set_health_check(self._health_check)
        else:
            self._circuit_breaker = None
            
        # Exponential backoff for retries
        backoff_config = BackoffConfig(
            initial_delay=0.5,
            max_delay=10.0,
            multiplier=1.5,
            jitter=True,
            max_retries=max_retries,
            strategy=BackoffStrategy.EXPONENTIAL
        )
        self._backoff = ExponentialBackoff(
            name=f"{service_name}_retry",
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
        
        # Register TTS-specific error patterns
        self._register_error_patterns()
        
        # Memory guard
        if enable_memory_guard:
            self._memory_guard = MemoryGuard(
                service_name=service_name,
                event_emitter=self._event_emitter,
                medium_threshold_mb=512,
                high_threshold_mb=1024,
                critical_threshold_mb=2048
            )
            
            # Register managed buffers
            self._memory_guard.register_managed_buffer(
                "streaming_buffer", self._streaming_buffer, max_size=1024
            )
        else:
            self._memory_guard = None
            
    def _register_error_patterns(self):
        """Register TTS-specific error patterns"""
        from ..reliability.error_handler import ErrorPattern
        
        # HTTP connection errors - retry
        self._error_handler.register_error_pattern(ErrorPattern(
            exception_type="ConnectError",
            level=ErrorLevel.WARNING,
            strategy=RecoveryStrategy.RETRY,
            max_occurrences=3,
            metadata={"escalate_to": RecoveryStrategy.FAILOVER}
        ))
        
        # HTTP timeout errors - retry with increased timeout
        self._error_handler.register_error_pattern(ErrorPattern(
            exception_type="TimeoutException",
            level=ErrorLevel.WARNING,
            strategy=RecoveryStrategy.RETRY,
            max_occurrences=2,
            metadata={"timeout_multiplier": 1.5}
        ))
        
        # Service unavailable - immediate failover
        self._error_handler.register_error_pattern(ErrorPattern(
            exception_type="HTTPStatusError",
            message_pattern="503",
            level=ErrorLevel.ERROR,
            strategy=RecoveryStrategy.FAILOVER,
            max_occurrences=1
        ))
        
        # Server errors - circuit break
        self._error_handler.register_error_pattern(ErrorPattern(
            exception_type="HTTPStatusError", 
            message_pattern="5[0-9][0-9]",
            level=ErrorLevel.ERROR,
            strategy=RecoveryStrategy.CIRCUIT_BREAK,
            max_occurrences=2
        ))
        
    def _setup_http_client(self):
        """Setup HTTP client with reliability features"""
        self._client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                keepalive_expiry=30.0
            ),
            timeout=httpx.Timeout(
                connect=self._connection_timeout,
                read=self._request_timeout,
                write=self._request_timeout,
                pool=self._request_timeout
            ),
            transport=httpx.AsyncHTTPTransport(
                retries=0  # We handle retries ourselves
            ),
            # Add retry behavior via httpx-retry if available
            event_hooks={
                'request': [self._log_request],
                'response': [self._log_response]
            }
        )
        
    async def _log_request(self, request):
        """Log outgoing requests for debugging"""
        logger.debug(f"TTS Request: {request.method} {request.url}")
        
    async def _log_response(self, response):
        """Log response details and update service stats"""
        logger.debug(f"TTS Response: {response.status_code} ({response.elapsed.total_seconds():.2f}s)")
        
        # Update service registry stats if available
        if self._service_registry:
            self._service_registry.update_service_stats(
                service_id=f"kokoro_tts_{self._base_url}",
                response_time_ms=response.elapsed.total_seconds() * 1000,
                success=(200 <= response.status_code < 300)
            )
            
    async def start(self, frame: SystemFrame):
        """Start the enhanced TTS service"""
        await super().start(frame)
        
        # Start reliability components
        if self._memory_guard:
            await self._memory_guard.start()
            
        # Perform initial health check
        await self._initial_health_check()
        
    async def stop(self):
        """Stop the enhanced TTS service"""
        await super().stop()
        
        # Cancel any ongoing request
        await self._cancel_current_request()
        
        # Stop reliability components
        if self._memory_guard:
            await self._memory_guard.stop()
            
        if self._circuit_breaker:
            await self._circuit_breaker.close()
            
        # Close HTTP client
        await self._client.aclose()
        
    async def _initial_health_check(self):
        """Perform initial health check"""
        try:
            is_healthy = await self._health_check()
            if not is_healthy:
                logger.warning("Initial health check failed, will use fallback if available")
                await self._switch_to_fallback("Initial health check failed")
        except Exception as e:
            logger.error(f"Initial health check error: {e}")
            
    async def _health_check(self) -> bool:
        """Health check for circuit breaker"""
        try:
            # Try a simple GET request to check service availability
            health_url = f"{self._base_url}/health"
            response = await asyncio.wait_for(
                self._client.get(health_url),
                timeout=5.0
            )
            return 200 <= response.status_code < 300
            
        except Exception:
            # If health endpoint doesn't exist, try the main endpoint
            try:
                response = await asyncio.wait_for(
                    self._client.get(self._base_url),
                    timeout=5.0
                )
                return 200 <= response.status_code < 500  # 4xx is ok, service is up
            except Exception:
                return False
                
    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """Enhanced TTS generation with reliability protection"""
        if self._using_fallback and self._fallback_tts:
            # Use fallback TTS
            async for frame in self._fallback_tts.run_tts(text):
                yield frame
            return
            
        try:
            # Use circuit breaker protection
            if self._circuit_breaker:
                async for frame in self._circuit_breaker.call(self._generate_tts_with_retry, text):
                    yield frame
            else:
                async for frame in self._generate_tts_with_retry(text):
                    yield frame
                    
        except CircuitBreakerOpenError:
            logger.warning("Circuit breaker open, switching to fallback TTS")
            await self._switch_to_fallback("Circuit breaker open")
            
            if self._fallback_tts:
                async for frame in self._fallback_tts.run_tts(text):
                    yield frame
            else:
                # Emit empty audio frame to maintain pipeline flow
                yield TTSAudioRawFrame(
                    audio=b'',
                    sample_rate=self._sample_rate,
                    num_channels=1
                )
                
        except Exception as e:
            recovery_strategy = await self._error_handler.handle_error(
                e, {"text": text[:100]}, "tts_generation"
            )
            
            if recovery_strategy == RecoveryStrategy.FAILOVER:
                await self._switch_to_fallback(str(e))
                if self._fallback_tts:
                    async for frame in self._fallback_tts.run_tts(text):
                        yield frame
                        
    async def _generate_tts_with_retry(self, text: str) -> AsyncGenerator[Frame, None]:
        """Generate TTS with retry logic"""
        try:
            async for frame in self._backoff.execute(
                self._generate_tts_internal,
                text,
                is_retriable=self._is_retriable
            ):
                yield frame
                
        except Exception as e:
            # Log final failure
            logger.error(f"TTS generation failed after retries: {e}")
            raise
            
    async def _generate_tts_internal(self, text: str) -> AsyncGenerator[Frame, None]:
        """Internal TTS generation logic"""
        # Cancel any existing request
        await self._cancel_current_request()
        
        # Prepare request
        request_data = {
            "model": "kokoro",
            "input": text,
            "voice": self._voice,
            "response_format": "wav",
            "stream": True,
            "continuous": True,
            "speed": self._speed,
            "volume_multiplier": 1.0,
            "stream_strip_silence": False,
            "normalize": True
        }
        
        # Start streaming request
        self._current_request = self._client.stream(
            "POST",
            f"{self._base_url}/v1/audio/speech",
            json=request_data
        )
        
        # Clear buffers
        self._audio_buffer = b""
        self._streaming_buffer = []
        wav_header_parsed = False
        kokoro_sample_rate = self._sample_rate
        
        try:
            async with self._current_request as response:
                response.raise_for_status()
                
                # Track performance
                start_time = time.time()
                total_bytes = 0
                
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                        
                    total_bytes += len(chunk)
                    
                    # Handle WAV header parsing
                    if not wav_header_parsed:
                        self._audio_buffer += chunk
                        if len(self._audio_buffer) >= 44:
                            try:
                                pcm_data, kokoro_sample_rate = self._extract_wav_data(self._audio_buffer)
                                wav_header_parsed = True
                                
                                if pcm_data:
                                    yield TTSAudioRawFrame(
                                        audio=pcm_data,
                                        sample_rate=kokoro_sample_rate,
                                        num_channels=1
                                    )
                                self._audio_buffer = b""
                            except Exception as e:
                                logger.debug(f"WAV header parsing failed: {e}")
                    else:
                        # Stream raw PCM data
                        yield TTSAudioRawFrame(
                            audio=chunk,
                            sample_rate=kokoro_sample_rate,
                            num_channels=1
                        )
                        
                # Handle remaining buffer
                if self._audio_buffer:
                    try:
                        frame = TTSAudioRawFrame(
                            audio=self._audio_buffer,
                            sample_rate=kokoro_sample_rate,
                            num_channels=1
                        )
                        yield frame
                    except Exception as e:
                        logger.warning(f"Failed to process final buffer: {e}")
                        
                # Log performance metrics
                duration = time.time() - start_time
                logger.debug(f"TTS completed: {total_bytes} bytes in {duration:.2f}s ({total_bytes/duration/1024:.1f} KB/s)")
                
                # Emit successful completion event
                if self._event_emitter:
                    await self._event_emitter.emit("tts_generation_complete", {
                        "text_length": len(text),
                        "audio_bytes": total_bytes,
                        "duration_seconds": duration,
                        "service": "kokoro"
                    })
                    
        finally:
            self._current_request = None
            
    def _is_retriable(self, exception: Exception) -> bool:
        """Determine if an exception should trigger a retry"""
        # Network errors are retriable
        if is_network_error(exception):
            return True
            
        # Service unavailable errors are retriable
        if is_service_unavailable_error(exception):
            return True
            
        # HTTP status errors
        if hasattr(exception, 'response') and hasattr(exception.response, 'status_code'):
            status_code = exception.response.status_code
            # Retry on server errors but not client errors
            return 500 <= status_code < 600
            
        # Timeout errors are retriable
        if isinstance(exception, (asyncio.TimeoutError, httpx.TimeoutException)):
            return True
            
        return False
        
    async def _cancel_current_request(self):
        """Cancel current HTTP request"""
        if self._current_request:
            try:
                await self._current_request.aclose()
            except Exception as e:
                logger.debug(f"Error cancelling request: {e}")
            finally:
                self._current_request = None
                
    async def _switch_to_fallback(self, reason: str):
        """Switch to fallback TTS service"""
        if not self._using_fallback:
            self._using_fallback = True
            logger.warning(f"Switching to fallback TTS: {reason}")
            
            if self._event_emitter:
                await self._event_emitter.emit("tts_fallback_activated", {
                    "reason": reason,
                    "primary_service": "kokoro",
                    "fallback_service": type(self._fallback_tts).__name__ if self._fallback_tts else None
                })
                
    async def recover_from_fallback(self):
        """Attempt to recover from fallback mode"""
        if self._using_fallback:
            is_healthy = await self._health_check()
            if is_healthy:
                self._using_fallback = False
                logger.info("Recovered from fallback, primary TTS service is healthy")
                
                if self._event_emitter:
                    await self._event_emitter.emit("tts_fallback_recovered", {
                        "service": "kokoro"
                    })
                    
    def _extract_wav_data(self, wav_bytes: bytes) -> tuple[bytes, int]:
        """Extract PCM data and sample rate from WAV bytes"""
        try:
            with io.BytesIO(wav_bytes) as wav_io:
                with wave.open(wav_io, 'rb') as wav_file:
                    sample_rate = wav_file.getframerate()
                    pcm_data = wav_file.readframes(wav_file.getnframes())
                    return pcm_data, sample_rate
        except Exception as e:
            logger.debug(f"Failed to parse WAV data: {e}")
            # Return raw data assuming Kokoro's default sample rate
            return wav_bytes, self._sample_rate
            
    def get_reliability_stats(self) -> Dict[str, Any]:
        """Get comprehensive reliability statistics"""
        stats = {
            "service_name": "kokoro_tts",
            "base_url": self._base_url,
            "using_fallback": self._using_fallback,
            "current_request_active": self._current_request is not None,
            "audio_buffer_size": len(self._audio_buffer),
            "streaming_buffer_size": len(self._streaming_buffer)
        }
        
        if self._circuit_breaker:
            stats["circuit_breaker"] = self._circuit_breaker.get_stats()
            
        if self._memory_guard:
            stats["memory"] = self._memory_guard.get_memory_stats()
            
        if self._error_handler:
            stats["errors"] = self._error_handler.get_error_stats()
            
        stats["backoff"] = self._backoff.get_stats()
        
        return stats