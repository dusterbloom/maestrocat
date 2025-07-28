# MaestroCat Reliability Framework
"""
Comprehensive error recovery and reliability framework for MaestroCat services.

This package provides:
- Circuit breaker patterns for external services
- Exponential backoff for reconnections
- Health check mechanisms
- Service registry for availability tracking
- Graceful degradation strategies
- Memory leak prevention
- Configuration management system
"""

from .circuit_breaker import CircuitBreaker, CircuitBreakerState, CircuitBreakerConfig, CircuitBreakerOpenError
from .health_monitor import HealthMonitor, ServiceHealth, HealthStatus, HealthCheck
from .service_registry import ServiceRegistry, ServiceInfo, ServiceType, ServiceEndpoint, LoadBalancingStrategy
from .backoff import ExponentialBackoff, BackoffConfig, BackoffStrategy, RetryableError, NonRetriableError, is_network_error, is_service_unavailable_error
from .error_handler import ErrorHandler, ErrorLevel, RecoveryStrategy, ErrorPattern, ErrorOccurrence, ErrorContext
from .memory_guard import MemoryGuard, MemoryThreshold, MemoryStats
from .config import (
    ReliabilityConfigManager, 
    GlobalReliabilityConfig, 
    ServiceReliabilityConfig, 
    ReliabilityProfile,
    get_config_manager,
    load_reliability_config
)

__all__ = [
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerState", 
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    
    # Health Monitoring
    "HealthMonitor", 
    "ServiceHealth",
    "HealthStatus",
    "HealthCheck",
    
    # Service Registry
    "ServiceRegistry",
    "ServiceInfo",
    "ServiceType",
    "ServiceEndpoint",
    "LoadBalancingStrategy",
    
    # Exponential Backoff
    "ExponentialBackoff",
    "BackoffConfig",
    "BackoffStrategy",
    "RetryableError",
    "NonRetriableError",
    "is_network_error",
    "is_service_unavailable_error",
    
    # Error Handling
    "ErrorHandler",
    "ErrorLevel",
    "RecoveryStrategy",
    "ErrorPattern",
    "ErrorOccurrence", 
    "ErrorContext",
    
    # Memory Management
    "MemoryGuard",
    "MemoryThreshold",
    "MemoryStats",
    
    # Configuration
    "ReliabilityConfigManager",
    "GlobalReliabilityConfig",
    "ServiceReliabilityConfig", 
    "ReliabilityProfile",
    "get_config_manager",
    "load_reliability_config"
]