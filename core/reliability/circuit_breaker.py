# Circuit Breaker Pattern Implementation
"""
Circuit breaker implementation for preventing cascading failures in MaestroCat services.
Provides automatic failure detection, service isolation, and recovery mechanisms.
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Callable, Any, Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Service unavailable, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 3          # Successes needed to close from half-open
    timeout: float = 60.0              # Seconds to wait before half-open
    request_timeout: float = 30.0      # Individual request timeout
    health_check_interval: float = 10.0  # Health check frequency when open
    

class CircuitBreaker:
    """
    Circuit breaker for protecting against cascading failures.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Service unavailable, requests fail fast
    - HALF_OPEN: Testing recovery, limited requests allowed
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        event_emitter = None
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._event_emitter = event_emitter
        
        # State tracking
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._next_attempt_time = 0.0
        
        # Statistics
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._blocked_requests = 0
        
        # Health checking
        self._health_check_task: Optional[asyncio.Task] = None
        self._health_check_callback: Optional[Callable] = None
        
    @property
    def state(self) -> CircuitBreakerState:
        """Current circuit breaker state"""
        return self._state
        
    @property
    def is_available(self) -> bool:
        """Whether the circuit allows requests"""
        return self._state in (CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN)
        
    def set_health_check(self, callback: Callable[[], bool]):
        """Set health check callback for automatic recovery testing"""
        self._health_check_callback = callback
        
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker protection.
        
        Args:
            func: Function to execute
            *args, **kwargs: Arguments for the function
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: When circuit is open
            Exception: Original function exceptions when circuit is closed/half-open
        """
        self._total_requests += 1
        
        # Check if circuit allows request
        if not self._should_allow_request():
            self._blocked_requests += 1
            await self._emit_event("request_blocked", {
                "reason": "circuit_open",
                "state": self._state.value
            })
            raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is open")
            
        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                self._execute_function(func, *args, **kwargs),
                timeout=self.config.request_timeout
            )
            await self._on_success()
            return result
            
        except asyncio.TimeoutError as e:
            await self._on_failure(e)
            raise
        except Exception as e:
            await self._on_failure(e)
            raise
            
    async def _execute_function(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function, handling both sync and async"""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
            
    def _should_allow_request(self) -> bool:
        """Determine if request should be allowed based on current state"""
        current_time = time.time()
        
        if self._state == CircuitBreakerState.CLOSED:
            return True
            
        elif self._state == CircuitBreakerState.OPEN:
            # Check if we should transition to half-open
            if current_time >= self._next_attempt_time:
                self._transition_to_half_open()
                return True
            return False
            
        elif self._state == CircuitBreakerState.HALF_OPEN:
            # Allow limited requests to test recovery
            return True
            
        return False
        
    async def _on_success(self):
        """Handle successful request"""
        self._successful_requests += 1
        
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._success_count += 1
            
            if self._success_count >= self.config.success_threshold:
                await self._transition_to_closed()
        
        # Reset failure count on success in any state
        self._failure_count = 0
        
    async def _on_failure(self, error: Exception):
        """Handle failed request"""
        self._failed_requests += 1
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        await self._emit_event("request_failed", {
            "error": str(error),
            "failure_count": self._failure_count
        })
        
        # Check if we should open circuit
        if self._state == CircuitBreakerState.CLOSED:
            if self._failure_count >= self.config.failure_threshold:
                await self._transition_to_open()
                
        elif self._state == CircuitBreakerState.HALF_OPEN:
            # Single failure in half-open immediately goes back to open
            await self._transition_to_open()
            
    async def _transition_to_closed(self):
        """Transition to CLOSED state"""
        old_state = self._state
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        
        await self._emit_event("state_changed", {
            "from": old_state.value,
            "to": self._state.value,
            "reason": "service_recovered"
        })
        
        logger.info(f"Circuit breaker '{self.name}' transitioned to CLOSED")
        
        # Stop health checking
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None
            
    async def _transition_to_open(self):
        """Transition to OPEN state"""
        old_state = self._state
        self._state = CircuitBreakerState.OPEN
        self._next_attempt_time = time.time() + self.config.timeout
        self._success_count = 0
        
        await self._emit_event("state_changed", {
            "from": old_state.value,
            "to": self._state.value,
            "reason": "failure_threshold_exceeded",
            "next_attempt": self._next_attempt_time
        })
        
        logger.warning(f"Circuit breaker '{self.name}' opened due to failures")
        
        # Start health checking
        if self._health_check_callback and not self._health_check_task:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state"""
        old_state = self._state
        self._state = CircuitBreakerState.HALF_OPEN
        self._success_count = 0
        
        logger.info(f"Circuit breaker '{self.name}' transitioned to HALF_OPEN")
        
    async def _health_check_loop(self):
        """Continuous health checking when circuit is open"""
        while self._state == CircuitBreakerState.OPEN:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                
                if self._health_check_callback:
                    if await self._execute_function(self._health_check_callback):
                        # Health check passed, transition to half-open
                        self._transition_to_half_open()
                        await self._emit_event("health_check_passed", {})
                        break
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Health check failed for '{self.name}': {e}")
                
    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit circuit breaker events"""
        if self._event_emitter:
            event_data = {
                "circuit_breaker": self.name,
                "state": self._state.value,
                **data
            }
            await self._event_emitter.emit(f"circuit_breaker_{event_type}", event_data)
            
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics"""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_requests": self._total_requests,
            "successful_requests": self._successful_requests,
            "failed_requests": self._failed_requests,
            "blocked_requests": self._blocked_requests,
            "success_rate": (
                self._successful_requests / max(1, self._total_requests) * 100
            ),
            "last_failure_time": self._last_failure_time,
            "next_attempt_time": self._next_attempt_time,
        }
        
    async def reset(self):
        """Reset circuit breaker to initial state"""
        old_state = self._state
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._next_attempt_time = 0.0
        
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None
            
        await self._emit_event("reset", {"previous_state": old_state.value})
        
    async def close(self):
        """Clean up circuit breaker resources"""
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocking requests"""
    pass