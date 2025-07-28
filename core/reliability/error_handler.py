# Error Handler and Recovery System
"""
Comprehensive error handling and recovery system for MaestroCat services.
Provides centralized error processing, recovery strategies, and event propagation.
"""

import asyncio
import time
import logging
import traceback
from enum import Enum
from typing import Dict, Any, Optional, Callable, List, Union, Type
from dataclasses import dataclass, field
import json

logger = logging.getLogger(__name__)


class ErrorLevel(Enum):
    """Error severity levels"""
    TRACE = "trace"
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RecoveryStrategy(Enum):
    """Error recovery strategies"""
    IGNORE = "ignore"              # Log and continue
    RETRY = "retry"                # Retry with backoff
    FAILOVER = "failover"          # Switch to fallback service
    CIRCUIT_BREAK = "circuit_break" # Open circuit breaker
    RESTART = "restart"            # Restart service/component
    ESCALATE = "escalate"          # Escalate to higher level handler
    ABORT = "abort"                # Stop processing


@dataclass
class ErrorPattern:
    """Pattern matching for error handling"""
    exception_type: Union[Type[Exception], str]
    message_pattern: Optional[str] = None
    code_pattern: Optional[str] = None
    level: ErrorLevel = ErrorLevel.ERROR
    strategy: RecoveryStrategy = RecoveryStrategy.RETRY
    max_occurrences: Optional[int] = None
    time_window: float = 300.0  # 5 minutes
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorOccurrence:
    """Individual error occurrence record"""
    error_id: str
    timestamp: float
    exception_type: str
    message: str
    stack_trace: str
    service_name: str
    component: str
    level: ErrorLevel
    recovery_strategy: RecoveryStrategy
    context: Dict[str, Any] = field(default_factory=dict)
    recovery_attempts: int = 0
    resolved: bool = False


class ErrorHandler:
    """
    Centralized error handling and recovery system.
    
    Features:
    - Pattern-based error classification
    - Configurable recovery strategies
    - Error rate tracking and circuit breaking
    - Event-driven error propagation
    - Error correlation and aggregation
    """
    
    def __init__(
        self,
        service_name: str,
        event_emitter = None,
        circuit_breaker = None,
        service_registry = None
    ):
        self.service_name = service_name
        self._event_emitter = event_emitter
        self._circuit_breaker = circuit_breaker
        self._service_registry = service_registry
        
        # Error patterns and handlers
        self._error_patterns: List[ErrorPattern] = []
        self._custom_handlers: Dict[str, Callable] = {}
        
        # Error tracking
        self._error_history: List[ErrorOccurrence] = []
        self._error_counts: Dict[str, int] = {}
        self._last_error_times: Dict[str, float] = {}
        
        # Configuration
        self.max_history_size = 1000
        self.error_rate_window = 300.0  # 5 minutes
        self.circuit_break_threshold = 10  # Errors per window
        
        # Default error patterns
        self._register_default_patterns()
        
    def _register_default_patterns(self):
        """Register default error patterns for common issues"""
        default_patterns = [
            # Network errors - retry with backoff
            ErrorPattern(
                exception_type=ConnectionError,
                level=ErrorLevel.WARNING,
                strategy=RecoveryStrategy.RETRY,
                max_occurrences=5,
                metadata={"max_retries": 3, "backoff_multiplier": 2.0}
            ),
            ErrorPattern(
                exception_type=TimeoutError,
                level=ErrorLevel.WARNING,
                strategy=RecoveryStrategy.RETRY,
                max_occurrences=3,
                metadata={"max_retries": 2, "timeout_increase": 1.5}
            ),
            
            # Service unavailable - failover
            ErrorPattern(
                exception_type="ServiceUnavailableError",
                level=ErrorLevel.ERROR,
                strategy=RecoveryStrategy.FAILOVER,
                max_occurrences=2
            ),
            
            # Memory errors - restart
            ErrorPattern(
                exception_type=MemoryError,
                level=ErrorLevel.CRITICAL,
                strategy=RecoveryStrategy.RESTART,
                max_occurrences=1
            ),
            
            # Programming errors - escalate
            ErrorPattern(
                exception_type=ValueError,
                level=ErrorLevel.ERROR,
                strategy=RecoveryStrategy.ESCALATE,
                max_occurrences=3
            ),
            ErrorPattern(
                exception_type=TypeError,
                level=ErrorLevel.ERROR,
                strategy=RecoveryStrategy.ESCALATE,
                max_occurrences=3
            ),
            
            # Websocket connection errors - retry then circuit break
            ErrorPattern(
                exception_type="ConnectionClosedError",
                level=ErrorLevel.WARNING,
                strategy=RecoveryStrategy.RETRY,
                max_occurrences=5,
                metadata={"escalate_to": RecoveryStrategy.CIRCUIT_BREAK}
            ),
            
            # HTTP errors
            ErrorPattern(
                exception_type="HTTPError",
                message_pattern="5[0-9][0-9]",  # 5xx server errors
                level=ErrorLevel.ERROR,
                strategy=RecoveryStrategy.FAILOVER,
                max_occurrences=3
            ),
            ErrorPattern(
                exception_type="HTTPError", 
                message_pattern="4[0-9][0-9]",  # 4xx client errors
                level=ErrorLevel.WARNING,
                strategy=RecoveryStrategy.IGNORE,
                max_occurrences=10
            )
        ]
        
        for pattern in default_patterns:
            self.register_error_pattern(pattern)
            
    def register_error_pattern(self, pattern: ErrorPattern):
        """Register an error pattern for handling"""
        self._error_patterns.append(pattern)
        logger.debug(f"Registered error pattern: {pattern.exception_type} -> {pattern.strategy.value}")
        
    def register_custom_handler(
        self,
        error_type: str,
        handler: Callable[[ErrorOccurrence], RecoveryStrategy]
    ):
        """Register a custom error handler function"""
        self._custom_handlers[error_type] = handler
        logger.debug(f"Registered custom handler for: {error_type}")
        
    async def handle_error(
        self,
        exception: Exception,
        context: Optional[Dict[str, Any]] = None,
        component: str = "unknown"
    ) -> RecoveryStrategy:
        """
        Handle an error and determine recovery strategy.
        
        Args:
            exception: The exception that occurred
            context: Additional context information
            component: Component where error occurred
            
        Returns:
            Recovery strategy to apply
        """
        # Create error occurrence record
        error_occurrence = self._create_error_occurrence(
            exception, context or {}, component
        )
        
        # Find matching pattern and determine strategy
        pattern = self._find_matching_pattern(exception)
        if pattern:
            error_occurrence.level = pattern.level
            error_occurrence.recovery_strategy = pattern.strategy
        else:
            # Default strategy for unmatched errors
            error_occurrence.level = ErrorLevel.ERROR
            error_occurrence.recovery_strategy = RecoveryStrategy.RETRY
            
        # Check for custom handler
        exception_type = type(exception).__name__
        if exception_type in self._custom_handlers:
            try:
                custom_strategy = self._custom_handlers[exception_type](error_occurrence)
                error_occurrence.recovery_strategy = custom_strategy
            except Exception as e:
                logger.error(f"Error in custom handler: {e}")
                
        # Update error tracking
        self._update_error_tracking(error_occurrence)
        
        # Check if we should escalate strategy
        escalated_strategy = self._check_escalation(error_occurrence, pattern)
        if escalated_strategy:
            error_occurrence.recovery_strategy = escalated_strategy
            
        # Execute recovery strategy
        await self._execute_recovery_strategy(error_occurrence)
        
        # Emit error event
        await self._emit_error_event(error_occurrence)
        
        # Check circuit breaker conditions
        await self._check_circuit_breaker(error_occurrence)
        
        return error_occurrence.recovery_strategy
        
    def _create_error_occurrence(
        self,
        exception: Exception,
        context: Dict[str, Any],
        component: str
    ) -> ErrorOccurrence:
        """Create error occurrence record"""
        error_id = f"{self.service_name}_{component}_{int(time.time() * 1000)}"
        
        return ErrorOccurrence(
            error_id=error_id,
            timestamp=time.time(),
            exception_type=type(exception).__name__,
            message=str(exception),
            stack_trace=traceback.format_exc(),
            service_name=self.service_name,
            component=component,
            level=ErrorLevel.ERROR,  # Will be updated by pattern matching
            recovery_strategy=RecoveryStrategy.RETRY,  # Will be updated
            context=context
        )
        
    def _find_matching_pattern(self, exception: Exception) -> Optional[ErrorPattern]:
        """Find the best matching error pattern"""
        exception_type = type(exception)
        exception_name = exception_type.__name__
        message = str(exception)
        
        # Look for exact type match first
        for pattern in self._error_patterns:
            if isinstance(pattern.exception_type, type):
                if isinstance(exception, pattern.exception_type):
                    if self._check_message_pattern(message, pattern.message_pattern):
                        return pattern
            else:
                # String-based type matching
                if pattern.exception_type == exception_name:
                    if self._check_message_pattern(message, pattern.message_pattern):
                        return pattern
                        
        return None
        
    def _check_message_pattern(
        self,
        message: str,
        pattern: Optional[str]
    ) -> bool:
        """Check if message matches pattern"""
        if not pattern:
            return True
            
        import re
        try:
            return bool(re.search(pattern, message))
        except re.error:
            logger.warning(f"Invalid regex pattern: {pattern}")
            return True
            
    def _update_error_tracking(self, error_occurrence: ErrorOccurrence):
        """Update error occurrence tracking"""
        error_key = f"{error_occurrence.exception_type}:{error_occurrence.component}"
        
        # Update counts
        self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1
        self._last_error_times[error_key] = error_occurrence.timestamp
        
        # Add to history
        self._error_history.append(error_occurrence)
        
        # Trim history if too large
        if len(self._error_history) > self.max_history_size:
            self._error_history = self._error_history[-self.max_history_size:]
            
    def _check_escalation(
        self,
        error_occurrence: ErrorOccurrence,
        pattern: Optional[ErrorPattern]
    ) -> Optional[RecoveryStrategy]:
        """Check if error should trigger strategy escalation"""
        if not pattern or not pattern.max_occurrences:
            return None
            
        error_key = f"{error_occurrence.exception_type}:{error_occurrence.component}"
        current_time = error_occurrence.timestamp
        time_window = pattern.time_window
        
        # Count recent occurrences
        recent_count = sum(
            1 for error in self._error_history
            if (error.exception_type == error_occurrence.exception_type and
                error.component == error_occurrence.component and
                current_time - error.timestamp <= time_window)
        )
        
        if recent_count >= pattern.max_occurrences:
            # Check for escalation strategy in metadata
            escalate_to = pattern.metadata.get("escalate_to")
            if escalate_to:
                logger.warning(f"Escalating {error_key}: {recent_count} occurrences in {time_window}s")
                return escalate_to
                
            # Default escalation: circuit break for retryable errors
            if pattern.strategy == RecoveryStrategy.RETRY:
                return RecoveryStrategy.CIRCUIT_BREAK
                
        return None
        
    async def _execute_recovery_strategy(self, error_occurrence: ErrorOccurrence):
        """Execute the determined recovery strategy"""
        strategy = error_occurrence.recovery_strategy
        
        if strategy == RecoveryStrategy.IGNORE:
            logger.info(f"Ignoring error: {error_occurrence.message}")
            
        elif strategy == RecoveryStrategy.FAILOVER:
            await self._execute_failover(error_occurrence)
            
        elif strategy == RecoveryStrategy.CIRCUIT_BREAK:
            await self._execute_circuit_break(error_occurrence)
            
        elif strategy == RecoveryStrategy.RESTART:
            await self._execute_restart(error_occurrence)
            
        elif strategy == RecoveryStrategy.ESCALATE:
            await self._execute_escalate(error_occurrence)
            
        # RETRY and ABORT are handled by the calling code
        
    async def _execute_failover(self, error_occurrence: ErrorOccurrence):
        """Execute failover recovery strategy"""
        if not self._service_registry:
            logger.warning("No service registry available for failover")
            return
            
        # Mark current service as degraded
        self._service_registry.mark_service_unavailable(
            self.service_name,
            f"Error: {error_occurrence.message}"
        )
        
        logger.warning(f"Executing failover for {self.service_name} due to: {error_occurrence.message}")
        
    async def _execute_circuit_break(self, error_occurrence: ErrorOccurrence):
        """Execute circuit breaker strategy"""
        if self._circuit_breaker:
            logger.warning(f"Opening circuit breaker due to: {error_occurrence.message}")
            # Circuit breaker will handle the logic internally
        else:
            logger.warning("No circuit breaker configured")
            
    async def _execute_restart(self, error_occurrence: ErrorOccurrence):
        """Execute restart recovery strategy"""
        logger.critical(f"Service restart required due to: {error_occurrence.message}")
        
        # Emit restart event - actual restart handled by service manager
        await self._emit_event("service_restart_required", {
            "service_name": self.service_name,
            "error_id": error_occurrence.error_id,
            "reason": error_occurrence.message
        })
        
    async def _execute_escalate(self, error_occurrence: ErrorOccurrence):
        """Execute escalation strategy"""
        logger.error(f"Escalating error: {error_occurrence.message}")
        
        # Emit escalation event
        await self._emit_event("error_escalated", {
            "service_name": self.service_name,
            "error_id": error_occurrence.error_id,
            "exception_type": error_occurrence.exception_type,
            "message": error_occurrence.message,
            "component": error_occurrence.component
        })
        
    async def _check_circuit_breaker(self, error_occurrence: ErrorOccurrence):
        """Check if error rate should trigger circuit breaker"""
        current_time = error_occurrence.timestamp
        
        # Count errors in the rate window
        recent_errors = [
            error for error in self._error_history
            if current_time - error.timestamp <= self.error_rate_window
        ]
        
        if len(recent_errors) >= self.circuit_break_threshold:
            if self._circuit_breaker:
                logger.error(f"High error rate detected: {len(recent_errors)} errors in {self.error_rate_window}s")
                # Let circuit breaker handle the decision
                
    async def _emit_error_event(self, error_occurrence: ErrorOccurrence):
        """Emit error event through event system"""
        await self._emit_event("error_occurred", {
            "error_id": error_occurrence.error_id,
            "service_name": self.service_name,
            "component": error_occurrence.component,
            "exception_type": error_occurrence.exception_type,
            "message": error_occurrence.message,
            "level": error_occurrence.level.value,
            "recovery_strategy": error_occurrence.recovery_strategy.value,
            "timestamp": error_occurrence.timestamp,
            "context": error_occurrence.context
        })
        
    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit event through event system"""
        if self._event_emitter:
            await self._event_emitter.emit(f"error_{event_type}", data)
            
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        current_time = time.time()
        
        # Calculate error rates
        recent_errors = [
            error for error in self._error_history
            if current_time - error.timestamp <= self.error_rate_window
        ]
        
        error_counts_by_type = {}
        error_counts_by_component = {}
        
        for error in recent_errors:
            # By type
            error_type = error.exception_type
            error_counts_by_type[error_type] = error_counts_by_type.get(error_type, 0) + 1
            
            # By component
            component = error.component
            error_counts_by_component[component] = error_counts_by_component.get(component, 0) + 1
            
        return {
            "service_name": self.service_name,
            "total_errors": len(self._error_history),
            "recent_errors": len(recent_errors),
            "error_rate_per_minute": len(recent_errors) / (self.error_rate_window / 60),
            "error_counts_by_type": error_counts_by_type,
            "error_counts_by_component": error_counts_by_component,
            "registered_patterns": len(self._error_patterns),
            "custom_handlers": len(self._custom_handlers),
            "timestamp": current_time
        }
        
    def clear_error_history(self, older_than_seconds: Optional[float] = None):
        """Clear error history"""
        if older_than_seconds:
            cutoff_time = time.time() - older_than_seconds
            self._error_history = [
                error for error in self._error_history
                if error.timestamp > cutoff_time
            ]
        else:
            self._error_history.clear()
            
        logger.info(f"Cleared error history for {self.service_name}")


class ErrorContext:
    """Context manager for error handling"""
    
    def __init__(
        self,
        error_handler: ErrorHandler,
        component: str,
        context: Optional[Dict[str, Any]] = None
    ):
        self.error_handler = error_handler
        self.component = component
        self.context = context or {}
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            await self.error_handler.handle_error(exc_val, self.context, self.component)
        return False  # Don't suppress the exception