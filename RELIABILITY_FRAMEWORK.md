# MaestroCat Reliability Framework

A comprehensive error recovery and reliability system for MaestroCat voice agents, designed to handle failures gracefully and maintain service availability in production environments.

## Overview

The MaestroCat Reliability Framework provides:

- **Circuit Breaker Protection**: Prevents cascade failures by isolating unhealthy services
- **Exponential Backoff**: Smart retry mechanisms with configurable strategies
- **Health Monitoring**: Real-time service health tracking and automatic recovery
- **Service Registry**: Centralized service discovery with failover capabilities
- **Memory Management**: Automatic memory leak detection and cleanup
- **Error Handling**: Pattern-based error classification and recovery strategies
- **Event-Driven Architecture**: Comprehensive error and performance event propagation

## Core Components

### 1. Circuit Breaker (`circuit_breaker.py`)

Implements the circuit breaker pattern to protect services from cascading failures.

```python
from core.reliability import CircuitBreaker, CircuitBreakerConfig

# Configure circuit breaker
config = CircuitBreakerConfig(
    failure_threshold=5,      # Open after 5 failures
    success_threshold=3,      # Close after 3 successes
    timeout=60.0,            # Wait 60s before half-open
    request_timeout=30.0,    # Individual request timeout
    health_check_interval=15.0
)

circuit_breaker = CircuitBreaker(
    name="whisperlive_stt",
    config=config,
    event_emitter=event_emitter
)

# Use circuit breaker protection
try:
    result = await circuit_breaker.call(risky_operation, arg1, arg2)
except CircuitBreakerOpenError:
    # Handle service unavailable
    result = await fallback_operation()
```

**States:**
- **CLOSED**: Normal operation, requests pass through
- **OPEN**: Service unavailable, requests fail fast
- **HALF_OPEN**: Testing recovery, limited requests allowed

### 2. Exponential Backoff (`backoff.py`)

Provides intelligent retry mechanisms with multiple strategies.

```python
from core.reliability import ExponentialBackoff, BackoffConfig, BackoffStrategy

config = BackoffConfig(
    initial_delay=1.0,
    max_delay=60.0,
    multiplier=2.0,
    jitter=True,
    max_retries=3,
    strategy=BackoffStrategy.EXPONENTIAL
)

backoff = ExponentialBackoff("service_retry", config, event_emitter)

# Execute with retry
result = await backoff.execute(
    unreliable_function,
    arg1, arg2,
    is_retriable=lambda e: isinstance(e, ConnectionError)
)
```

**Strategies:**
- **EXPONENTIAL**: Delay doubles each attempt
- **LINEAR**: Delay increases linearly
- **FIXED**: Constant delay between attempts
- **FIBONACCI**: Fibonacci sequence delays

### 3. Health Monitor (`health_monitor.py`)

Comprehensive health monitoring with automatic recovery triggering.

```python
from core.reliability import HealthMonitor, HealthCheck

monitor = HealthMonitor(event_emitter=event_emitter)

# Register HTTP service
monitor.register_http_service(
    service_name="kokoro_tts",
    base_url="http://localhost:5000",
    health_endpoint="/health",
    interval=30.0
)

# Register WebSocket service
monitor.register_websocket_service(
    service_name="whisperlive_stt", 
    websocket_url="ws://localhost:9090",
    interval=15.0
)

# Register recovery callback
monitor.register_recovery_callback(
    "kokoro_tts",
    lambda health: restart_service_if_unhealthy(health)
)

await monitor.start()
```

### 4. Service Registry (`service_registry.py`)

Centralized service discovery with load balancing and failover.

```python
from core.reliability import ServiceRegistry, ServiceInfo, ServiceType, ServiceEndpoint

registry = ServiceRegistry(event_emitter=event_emitter)

# Register service
service_info = ServiceInfo(
    service_id="kokoro_tts_primary",
    service_type=ServiceType.TTS,
    name="Kokoro TTS Primary",
    version="1.0.0",
    endpoints=[ServiceEndpoint("http", "localhost", 5000)],
    priority=100,
    capabilities={"voices": ["af_bella", "af_sarah"], "streaming": True}
)

registry.register_service(service_info)

# Discover service
service = registry.discover_service(
    ServiceType.TTS,
    capabilities={"streaming": True}
)

# Set fallback chain
registry.set_fallback_chain(
    ServiceType.TTS,
    ["kokoro_tts_primary", "macos_tts_fallback"]
)
```

### 5. Error Handler (`error_handler.py`)

Pattern-based error handling with configurable recovery strategies.

```python
from core.reliability import ErrorHandler, ErrorPattern, ErrorLevel, RecoveryStrategy

handler = ErrorHandler(
    service_name="whisperlive_stt",
    event_emitter=event_emitter,
    circuit_breaker=circuit_breaker,
    service_registry=registry
)

# Register error patterns
handler.register_error_pattern(ErrorPattern(
    exception_type=ConnectionError,
    level=ErrorLevel.WARNING,
    strategy=RecoveryStrategy.RETRY,
    max_occurrences=3,
    metadata={"escalate_to": RecoveryStrategy.CIRCUIT_BREAK}
))

# Handle errors
try:
    result = await risky_operation()
except Exception as e:
    strategy = await handler.handle_error(e, {"operation": "connect"}, "websocket")
    if strategy == RecoveryStrategy.FAILOVER:
        result = await fallback_operation()
```

### 6. Memory Guard (`memory_guard.py`)

Automatic memory leak detection and prevention.

```python
from core.reliability import MemoryGuard

guard = MemoryGuard(
    service_name="whisperlive_stt",
    event_emitter=event_emitter,
    medium_threshold_mb=512,
    high_threshold_mb=1024,
    critical_threshold_mb=2048
)

# Register managed buffers
guard.register_managed_buffer("audio_buffer", audio_buffer, max_size=32768)
guard.register_managed_buffer("processed_segments", segment_set, max_size=100)

await guard.start()

# Track objects for leak detection
guard.track_object(large_object)
```

## Enhanced Service Implementations

### Reliable WhisperLive STT Service

```python
from core.services import ReliableWhisperLiveSTTService

stt_service = ReliableWhisperLiveSTTService(
    host="localhost",
    port=9090,
    language="en",
    model="small",
    event_emitter=event_emitter,
    service_registry=registry,
    
    # Reliability features
    enable_circuit_breaker=True,
    enable_health_monitoring=True,
    enable_memory_guard=True,
    fallback_to_silence=True
)

# Get reliability statistics
stats = stt_service.get_reliability_stats()
print(f"Circuit breaker state: {stats['circuit_breaker']['state']}")
print(f"Memory usage: {stats['memory']['current_memory_mb']}MB")
```

### Reliable Kokoro TTS Service

```python
from core.services import ReliableKokoroTTSService

tts_service = ReliableKokoroTTSService(
    base_url="http://localhost:5000",
    voice="af_bella",
    speed=1.0,
    event_emitter=event_emitter,
    service_registry=registry,
    
    # Reliability features
    enable_circuit_breaker=True,
    enable_health_monitoring=True,
    enable_memory_guard=True,
    fallback_tts=macos_tts_service,
    
    # HTTP configuration
    max_retries=2,
    request_timeout=30.0,
    connection_timeout=5.0
)
```

## Configuration Management

### Using Configuration Profiles

```python
from core.reliability.config import load_reliability_config, ReliabilityProfile

# Load predefined profile
config = load_reliability_config(profile=ReliabilityProfile.PRODUCTION)

# Load from file
config = load_reliability_config(config_file="config/reliability.yaml")

# Load from environment variables
config = load_reliability_config(from_env=True)

# Get service-specific configuration
service_config = config.get_service_config("whisperlive_stt")
circuit_config = config.get_circuit_breaker_config("whisperlive_stt")
```

### Configuration File Structure

```yaml
# config/reliability.yaml
default_service:
  circuit_breaker_enabled: true
  circuit_breaker_failure_threshold: 5
  backoff_max_retries: 3
  memory_guard_enabled: true
  memory_high_threshold_mb: 1024

services:
  whisperlive_stt:
    circuit_breaker_failure_threshold: 3
    memory_medium_threshold_mb: 256
    service_specific:
      reconnect_on_close: true
      max_audio_buffer_size: 32768
```

## Event System Integration

The reliability framework integrates with MaestroCat's event system to provide real-time monitoring and debugging capabilities.

### Key Events

```python
# Circuit breaker events
await event_emitter.emit("circuit_breaker_state_changed", {
    "circuit_breaker": "whisperlive_stt",
    "from": "closed",
    "to": "open",
    "reason": "failure_threshold_exceeded"
})

# Health monitoring events  
await event_emitter.emit("health_service_status_changed", {
    "service": "kokoro_tts",
    "old_status": "healthy",
    "new_status": "unhealthy",
    "error_message": "Connection timeout"
})

# Memory events
await event_emitter.emit("memory_critical_memory_usage", {
    "service_name": "whisperlive_stt",
    "memory_mb": 2048,
    "action": "emergency_cleanup"
})

# Error events
await event_emitter.emit("error_error_occurred", {
    "service_name": "kokoro_tts",
    "exception_type": "ConnectionError",
    "recovery_strategy": "retry",
    "level": "warning"
})
```

## Best Practices

### 1. Service Configuration

- Use **PRODUCTION** profile for production deployments
- Configure appropriate **memory thresholds** based on expected usage
- Set **circuit breaker timeouts** based on service recovery time
- Enable **health monitoring** for all critical services

### 2. Error Handling

- Register **service-specific error patterns** for better recovery
- Use **exponential backoff** for transient failures
- Implement **graceful degradation** with fallback services
- Monitor **error rates** and adjust thresholds accordingly

### 3. Memory Management

- Register **large buffers** with the memory guard
- Set appropriate **memory thresholds** for your deployment
- Enable **tracemalloc** in development for leak detection
- Implement **buffer size limits** to prevent unbounded growth

### 4. Monitoring and Observability

- Subscribe to **reliability events** for monitoring
- Implement **custom dashboards** using event data
- Set up **alerts** for critical reliability events
- Monitor **service health** and **circuit breaker states**

### 5. Testing

- Test **failure scenarios** in development
- Verify **circuit breaker behavior** under load
- Test **fallback strategies** and recovery mechanisms
- Monitor **memory usage** during long-running tests

## Integration Example

```python
import asyncio
from core.pipeline.extension_points import create_reliable_pipeline
from core.reliability.config import load_reliability_config, ReliabilityProfile

async def main():
    # Load reliability configuration
    config = load_reliability_config(
        profile=ReliabilityProfile.PRODUCTION,
        config_file="config/reliability.yaml"
    )
    
    # Create pipeline with reliability features
    pipeline = await create_reliable_pipeline(
        config_file="config/maestrocat.yaml",
        reliability_config=config,
        enable_monitoring=True,
        enable_debug_ui=True
    )
    
    # Start pipeline
    await pipeline.start()
    
    # Monitor reliability stats
    async def monitor_stats():
        while True:
            await asyncio.sleep(60)
            stats = pipeline.get_reliability_stats()
            
            # Check circuit breaker states
            for service, service_stats in stats["services"].items():
                if service_stats.get("circuit_breaker", {}).get("state") == "open":
                    print(f"WARNING: {service} circuit breaker is open")
                    
            # Check memory usage
            for service, service_stats in stats["services"].items():
                memory_mb = service_stats.get("memory", {}).get("current_memory_mb", 0)
                if memory_mb > 1024:
                    print(f"WARNING: {service} high memory usage: {memory_mb}MB")
    
    # Start monitoring task
    monitor_task = asyncio.create_task(monitor_stats())
    
    try:
        # Run pipeline
        await pipeline.run()
    finally:
        monitor_task.cancel()
        await pipeline.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Docker Service Health Monitoring

For Docker-based services, the framework provides automatic health checking and restart capabilities:

```python
from core.reliability import DockerServiceManager

# Automatic Docker service management
docker_manager = DockerServiceManager(
    event_emitter=event_emitter,
    compose_file="docker-compose.yml"
)

# Register services for monitoring
docker_manager.register_service("whisperlive", health_check_url="http://localhost:9090/health")
docker_manager.register_service("kokoro", health_check_url="http://localhost:5000/health")

# Auto-restart unhealthy services
await docker_manager.start_monitoring()
```

This comprehensive reliability framework ensures that MaestroCat voice agents can operate reliably in production environments, automatically recovering from common failure scenarios and providing detailed observability into system health and performance.