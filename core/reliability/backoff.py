# Exponential Backoff Implementation
"""
Exponential backoff with jitter for retry mechanisms in MaestroCat services.
Prevents thundering herd problems and provides configurable retry strategies.
"""

import asyncio
import random
import time
import logging
from typing import Optional, Callable, Any, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class BackoffStrategy(Enum):
    """Different backoff strategies"""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"
    FIBONACCI = "fibonacci"


@dataclass
class BackoffConfig:
    """Configuration for backoff behavior"""
    initial_delay: float = 1.0          # Initial delay in seconds
    max_delay: float = 300.0            # Maximum delay in seconds
    multiplier: float = 2.0             # Backoff multiplier for exponential
    jitter: bool = True                 # Add randomness to prevent thundering herd
    max_retries: Optional[int] = None   # Maximum retry attempts (None = infinite)
    strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL


class ExponentialBackoff:
    """
    Exponential backoff implementation with jitter and multiple strategies.
    
    Features:
    - Multiple backoff strategies (exponential, linear, fixed, fibonacci)
    - Configurable jitter to prevent thundering herd
    - Maximum retry limits
    - Detailed retry statistics
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[BackoffConfig] = None,
        event_emitter = None
    ):
        self.name = name
        self.config = config or BackoffConfig()
        self._event_emitter = event_emitter
        
        # State tracking
        self._attempt_count = 0
        self._total_delay = 0.0
        self._start_time = 0.0
        self._fibonacci_sequence = [1, 1]  # For fibonacci backoff
        
    @property
    def attempt_count(self) -> int:
        """Number of retry attempts made"""
        return self._attempt_count
        
    @property
    def total_delay(self) -> float:
        """Total time spent in backoff delays"""
        return self._total_delay
        
    async def execute(
        self,
        func: Callable,
        *args,
        is_retriable: Optional[Callable[[Exception], bool]] = None,
        **kwargs
    ) -> Any:
        """
        Execute function with exponential backoff on failures.
        
        Args:
            func: Function to execute
            *args, **kwargs: Arguments for the function
            is_retriable: Function to determine if exception is retriable
            
        Returns:
            Function result
            
        Raises:
            Exception: Last exception if max retries exceeded
        """
        self._attempt_count = 0
        self._total_delay = 0.0
        self._start_time = time.time()
        last_exception = None
        
        while True:
            self._attempt_count += 1
            
            try:
                # Execute function
                result = await self._execute_function(func, *args, **kwargs)
                
                # Success - emit event and return
                if self._attempt_count > 1:
                    await self._emit_event("retry_succeeded", {
                        "attempts": self._attempt_count,
                        "total_delay": self._total_delay,
                        "duration": time.time() - self._start_time
                    })
                    
                return result
                
            except Exception as e:
                last_exception = e
                
                # Check if we should retry
                if not self._should_retry(e, is_retriable):
                    await self._emit_event("retry_abandoned", {
                        "reason": "non_retriable_error",
                        "error": str(e),
                        "attempts": self._attempt_count
                    })
                    raise e
                    
                # Check max retries
                if (self.config.max_retries is not None and 
                    self._attempt_count >= self.config.max_retries):
                    await self._emit_event("retry_exhausted", {
                        "max_retries": self.config.max_retries,
                        "last_error": str(e),
                        "total_delay": self._total_delay
                    })
                    raise e
                    
                # Calculate delay and wait
                delay = self._calculate_delay()
                self._total_delay += delay
                
                await self._emit_event("retry_attempt", {
                    "attempt": self._attempt_count,
                    "delay": delay,
                    "error": str(e)
                })
                
                logger.info(f"Retrying '{self.name}' in {delay:.2f}s (attempt {self._attempt_count})")
                await asyncio.sleep(delay)
                
    async def _execute_function(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function, handling both sync and async"""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
            
    def _should_retry(
        self,
        exception: Exception,
        is_retriable: Optional[Callable[[Exception], bool]]
    ) -> bool:
        """Determine if exception should trigger a retry"""
        if is_retriable:
            return is_retriable(exception)
            
        # Default retriable exceptions
        retriable_types = (
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError,
            OSError,  # Network-related OS errors
        )
        
        # Don't retry on programming errors
        non_retriable_types = (
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
        )
        
        if isinstance(exception, non_retriable_types):
            return False
            
        if isinstance(exception, retriable_types):
            return True
            
        # For HTTP errors, check status codes
        if hasattr(exception, 'status_code'):
            # Retry on server errors (5xx) but not client errors (4xx)
            return 500 <= exception.status_code < 600
            
        # Default to retrying unknown exceptions
        return True
        
    def _calculate_delay(self) -> float:
        """Calculate delay for current attempt"""
        if self.config.strategy == BackoffStrategy.EXPONENTIAL:
            delay = self.config.initial_delay * (self.config.multiplier ** (self._attempt_count - 1))
            
        elif self.config.strategy == BackoffStrategy.LINEAR:
            delay = self.config.initial_delay * self._attempt_count
            
        elif self.config.strategy == BackoffStrategy.FIXED:
            delay = self.config.initial_delay
            
        elif self.config.strategy == BackoffStrategy.FIBONACCI:
            # Ensure fibonacci sequence is long enough
            while len(self._fibonacci_sequence) < self._attempt_count:
                next_fib = self._fibonacci_sequence[-1] + self._fibonacci_sequence[-2]
                self._fibonacci_sequence.append(next_fib)
                
            delay = self.config.initial_delay * self._fibonacci_sequence[self._attempt_count - 1]
            
        else:
            delay = self.config.initial_delay
            
        # Apply maximum delay limit
        delay = min(delay, self.config.max_delay)
        
        # Add jitter if enabled
        if self.config.jitter:
            # Add up to 25% jitter
            jitter_amount = delay * 0.25 * random.random()
            delay += jitter_amount
            
        return delay
        
    async def _emit_event(self, event_type: str, data: dict):
        """Emit backoff events"""
        if self._event_emitter:
            event_data = {
                "backoff_name": self.name,
                "strategy": self.config.strategy.value,
                **data
            }
            await self._event_emitter.emit(f"backoff_{event_type}", event_data)
            
    def reset(self):
        """Reset backoff state"""
        self._attempt_count = 0
        self._total_delay = 0.0
        self._start_time = 0.0
        self._fibonacci_sequence = [1, 1]
        
    def get_stats(self) -> dict:
        """Get backoff statistics"""
        return {
            "name": self.name,
            "strategy": self.config.strategy.value,
            "attempts": self._attempt_count,
            "total_delay": self._total_delay,
            "average_delay": self._total_delay / max(1, self._attempt_count - 1),
            "config": {
                "initial_delay": self.config.initial_delay,
                "max_delay": self.config.max_delay,
                "multiplier": self.config.multiplier,
                "jitter": self.config.jitter,
                "max_retries": self.config.max_retries
            }
        }


class RetryableError(Exception):
    """Exception that explicitly indicates a retriable error"""
    pass


class NonRetriableError(Exception):
    """Exception that explicitly indicates a non-retriable error"""
    pass


def is_network_error(exception: Exception) -> bool:
    """Helper function to identify network-related errors"""
    network_error_types = (
        ConnectionError,
        ConnectionRefusedError,
        ConnectionResetError,
        ConnectionAbortedError,
        TimeoutError,
        asyncio.TimeoutError,
        OSError,
    )
    
    if isinstance(exception, network_error_types):
        return True
        
    # Check for websocket errors
    if hasattr(exception, '__module__'):
        if 'websocket' in exception.__module__.lower():
            return True
            
    # Check for HTTP errors
    if hasattr(exception, 'status_code'):
        # Network errors or server errors
        return exception.status_code >= 500 or exception.status_code in [0, 408, 429]
        
    return False


def is_service_unavailable_error(exception: Exception) -> bool:
    """Helper function to identify service unavailability errors"""
    if hasattr(exception, 'status_code'):
        # Service unavailable, bad gateway, gateway timeout
        return exception.status_code in [503, 502, 504]
        
    if isinstance(exception, ConnectionRefusedError):
        return True
        
    return False