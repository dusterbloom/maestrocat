# Health Monitoring System
"""
Comprehensive health monitoring for MaestroCat services.
Provides real-time health checks, service availability tracking, and automatic recovery.
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Dict, Any, Optional, Callable, List, Set
from dataclasses import dataclass, field
import httpx
import websockets
import psutil
import gc

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Service health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Individual health check configuration"""
    name: str
    check_func: Callable[[], bool]
    interval: float = 30.0              # Check interval in seconds
    timeout: float = 10.0               # Check timeout
    critical: bool = True               # Whether failure affects overall health
    consecutive_failures_threshold: int = 3  # Failures before marking unhealthy


@dataclass 
class ServiceHealth:
    """Health information for a service"""
    service_name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check_time: float = 0.0
    response_time_ms: float = 0.0
    error_message: Optional[str] = None
    consecutive_failures: int = 0
    total_checks: int = 0
    successful_checks: int = 0
    uptime_percentage: float = 100.0
    checks: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class HealthMonitor:
    """
    Comprehensive health monitoring system for MaestroCat services.
    
    Features:
    - Multiple health check types (HTTP, WebSocket, function-based)
    - Configurable check intervals and thresholds
    - Automatic service recovery triggering
    - Health history and trending
    - Integration with circuit breakers
    """
    
    def __init__(
        self,
        event_emitter = None,
        enable_system_metrics: bool = True,
        memory_threshold_mb: int = 1024,
        cpu_threshold_percent: float = 80.0
    ):
        self._event_emitter = event_emitter
        self.enable_system_metrics = enable_system_metrics
        self.memory_threshold_mb = memory_threshold_mb
        self.cpu_threshold_percent = cpu_threshold_percent
        
        # Service tracking
        self._services: Dict[str, ServiceHealth] = {}
        self._health_checks: Dict[str, List[HealthCheck]] = {}
        self._check_tasks: Dict[str, List[asyncio.Task]] = {}
        
        # System monitoring
        self._system_check_task: Optional[asyncio.Task] = None
        self._system_health = ServiceHealth("system")
        
        # Recovery callbacks
        self._recovery_callbacks: Dict[str, List[Callable]] = {}
        
        # HTTP client for health checks
        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        
    async def start(self):
        """Start health monitoring"""
        logger.info("Starting health monitoring system")
        
        # Start system monitoring if enabled
        if self.enable_system_metrics:
            self._system_check_task = asyncio.create_task(self._system_health_loop())
            
        # Start service health checks
        for service_name in self._health_checks:
            await self._start_service_checks(service_name)
            
        await self._emit_event("health_monitor_started", {})
        
    async def stop(self):
        """Stop health monitoring"""
        logger.info("Stopping health monitoring system")
        
        # Stop system monitoring
        if self._system_check_task:
            self._system_check_task.cancel()
            
        # Stop all service checks
        for tasks in self._check_tasks.values():
            for task in tasks:
                task.cancel()
                
        await self._http_client.aclose()
        await self._emit_event("health_monitor_stopped", {})
        
    def register_service(
        self,
        service_name: str,
        health_checks: List[HealthCheck]
    ):
        """Register a service for health monitoring"""
        self._services[service_name] = ServiceHealth(service_name)
        self._health_checks[service_name] = health_checks
        self._check_tasks[service_name] = []
        
        logger.info(f"Registered service '{service_name}' with {len(health_checks)} health checks")
        
    def register_http_service(
        self,
        service_name: str,
        base_url: str,
        health_endpoint: str = "/health",
        interval: float = 30.0,
        timeout: float = 10.0,
        critical: bool = True
    ):
        """Register HTTP service for health monitoring"""
        health_check = HealthCheck(
            name=f"{service_name}_http",
            check_func=lambda: self._check_http_health(f"{base_url}{health_endpoint}"),
            interval=interval,
            timeout=timeout,
            critical=critical
        )
        self.register_service(service_name, [health_check])
        
    def register_websocket_service(
        self,
        service_name: str,
        websocket_url: str,
        interval: float = 30.0,
        timeout: float = 10.0,
        critical: bool = True
    ):
        """Register WebSocket service for health monitoring"""
        health_check = HealthCheck(
            name=f"{service_name}_websocket",
            check_func=lambda: self._check_websocket_health(websocket_url),
            interval=interval,
            timeout=timeout,
            critical=critical
        )
        self.register_service(service_name, [health_check])
        
    def register_recovery_callback(
        self,
        service_name: str,
        callback: Callable[[ServiceHealth], None]
    ):
        """Register callback to trigger when service becomes unhealthy"""
        if service_name not in self._recovery_callbacks:
            self._recovery_callbacks[service_name] = []
        self._recovery_callbacks[service_name].append(callback)
        
    async def _start_service_checks(self, service_name: str):
        """Start health checks for a service"""
        if service_name not in self._health_checks:
            return
            
        for health_check in self._health_checks[service_name]:
            task = asyncio.create_task(
                self._health_check_loop(service_name, health_check)
            )
            self._check_tasks[service_name].append(task)
            
    async def _health_check_loop(self, service_name: str, health_check: HealthCheck):
        """Continuous health checking loop for a service"""
        while True:
            try:
                await asyncio.sleep(health_check.interval)
                await self._perform_health_check(service_name, health_check)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop for {service_name}: {e}")
                
    async def _perform_health_check(self, service_name: str, health_check: HealthCheck):
        """Perform individual health check"""
        service = self._services[service_name]
        start_time = time.time()
        
        try:
            # Execute health check with timeout
            result = await asyncio.wait_for(
                self._execute_health_check(health_check.check_func),
                timeout=health_check.timeout
            )
            
            # Calculate response time
            response_time = (time.time() - start_time) * 1000
            
            # Update service health
            service.last_check_time = time.time()
            service.response_time_ms = response_time
            service.total_checks += 1
            
            if result:
                # Health check passed
                service.successful_checks += 1
                service.consecutive_failures = 0
                service.error_message = None
                
                # Update status based on critical checks
                if health_check.critical:
                    service.status = HealthStatus.HEALTHY
                    
            else:
                # Health check failed
                service.consecutive_failures += 1
                service.error_message = f"Health check '{health_check.name}' failed"
                
                # Update status if critical
                if health_check.critical:
                    if service.consecutive_failures >= health_check.consecutive_failures_threshold:
                        await self._mark_service_unhealthy(service_name, service.error_message)
                    else:
                        service.status = HealthStatus.DEGRADED
                        
            # Update uptime percentage
            service.uptime_percentage = (service.successful_checks / service.total_checks) * 100
            
            # Store check details
            service.checks[health_check.name] = {
                "status": "passed" if result else "failed",
                "response_time_ms": response_time,
                "timestamp": service.last_check_time
            }
            
            # Emit health check event
            await self._emit_event("health_check_completed", {
                "service": service_name,
                "check": health_check.name,
                "status": service.status.value,
                "response_time_ms": response_time,
                "result": result
            })
            
        except asyncio.TimeoutError:
            await self._handle_health_check_error(
                service_name, health_check, "Health check timed out"
            )
        except Exception as e:
            await self._handle_health_check_error(
                service_name, health_check, str(e)
            )
            
    async def _execute_health_check(self, check_func: Callable) -> bool:
        """Execute health check function"""
        if asyncio.iscoroutinefunction(check_func):
            return await check_func()
        else:
            return check_func()
            
    async def _handle_health_check_error(
        self,
        service_name: str,
        health_check: HealthCheck,
        error_message: str
    ):
        """Handle health check errors"""
        service = self._services[service_name]
        service.consecutive_failures += 1
        service.total_checks += 1
        service.error_message = error_message
        service.last_check_time = time.time()
        
        # Update status if critical
        if health_check.critical:
            if service.consecutive_failures >= health_check.consecutive_failures_threshold:
                await self._mark_service_unhealthy(service_name, error_message)
            else:
                service.status = HealthStatus.DEGRADED
                
        # Update uptime percentage
        service.uptime_percentage = (service.successful_checks / service.total_checks) * 100
        
        logger.warning(f"Health check failed for {service_name}: {error_message}")
        
    async def _mark_service_unhealthy(self, service_name: str, error_message: str):
        """Mark service as unhealthy and trigger recovery"""
        service = self._services[service_name]
        old_status = service.status
        service.status = HealthStatus.UNHEALTHY
        
        # Emit status change event
        await self._emit_event("service_status_changed", {
            "service": service_name,
            "old_status": old_status.value,
            "new_status": service.status.value,
            "error_message": error_message
        })
        
        # Trigger recovery callbacks
        if service_name in self._recovery_callbacks:
            for callback in self._recovery_callbacks[service_name]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(service)
                    else:
                        callback(service)
                except Exception as e:
                    logger.error(f"Error in recovery callback for {service_name}: {e}")
                    
        logger.error(f"Service {service_name} marked as unhealthy: {error_message}")
        
    async def _check_http_health(self, url: str) -> bool:
        """Check HTTP service health"""
        try:
            response = await self._http_client.get(url)
            return 200 <= response.status_code < 300
        except Exception:
            return False
            
    async def _check_websocket_health(self, url: str) -> bool:
        """Check WebSocket service health"""
        try:
            async with websockets.connect(url, timeout=5) as websocket:
                # Send ping and wait for pong
                await websocket.ping()
                return True
        except Exception:
            return False
            
    async def _system_health_loop(self):
        """Monitor system health metrics"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                await self._check_system_health()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in system health monitoring: {e}")
                
    async def _check_system_health(self):
        """Check system resource health"""
        try:
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            memory_mb = memory.used / (1024 * 1024)
            
            # Check Python process metrics
            process = psutil.Process()
            process_memory_mb = process.memory_info().rss / (1024 * 1024)
            
            # Determine health status
            status = HealthStatus.HEALTHY
            issues = []
            
            if cpu_percent > self.cpu_threshold_percent:
                status = HealthStatus.DEGRADED
                issues.append(f"High CPU usage: {cpu_percent:.1f}%")
                
            if process_memory_mb > self.memory_threshold_mb:
                status = HealthStatus.DEGRADED
                issues.append(f"High memory usage: {process_memory_mb:.1f}MB")
                
            # Force garbage collection if memory is high
            if process_memory_mb > self.memory_threshold_mb * 0.8:
                gc.collect()
                
            # Update system health
            self._system_health.status = status
            self._system_health.last_check_time = time.time()
            self._system_health.error_message = "; ".join(issues) if issues else None
            self._system_health.metadata = {
                "cpu_percent": cpu_percent,
                "memory_mb": memory_mb,
                "process_memory_mb": process_memory_mb,
                "memory_percent": memory.percent
            }
            
            # Emit system health event
            await self._emit_event("system_health_check", {
                "status": status.value,
                "cpu_percent": cpu_percent,
                "memory_mb": memory_mb,
                "process_memory_mb": process_memory_mb,
                "issues": issues
            })
            
        except Exception as e:
            logger.error(f"Error checking system health: {e}")
            
    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit health monitoring events"""
        if self._event_emitter:
            await self._event_emitter.emit(f"health_{event_type}", data)
            
    def get_service_health(self, service_name: str) -> Optional[ServiceHealth]:
        """Get health information for a service"""
        return self._services.get(service_name)
        
    def get_all_services_health(self) -> Dict[str, ServiceHealth]:
        """Get health information for all services"""
        return self._services.copy()
        
    def get_system_health(self) -> ServiceHealth:
        """Get system health information"""
        return self._system_health
        
    def get_overall_health(self) -> HealthStatus:
        """Get overall system health status"""
        # Check if any critical services are unhealthy
        unhealthy_services = [
            name for name, service in self._services.items()
            if service.status == HealthStatus.UNHEALTHY
        ]
        
        if unhealthy_services:
            return HealthStatus.UNHEALTHY
            
        # Check if any services are degraded
        degraded_services = [
            name for name, service in self._services.items() 
            if service.status == HealthStatus.DEGRADED
        ]
        
        if degraded_services or self._system_health.status == HealthStatus.DEGRADED:
            return HealthStatus.DEGRADED
            
        return HealthStatus.HEALTHY
        
    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary"""
        return {
            "overall_status": self.get_overall_health().value,
            "system_health": {
                "status": self._system_health.status.value,
                "metadata": self._system_health.metadata
            },
            "services": {
                name: {
                    "status": service.status.value,
                    "uptime_percentage": service.uptime_percentage,
                    "response_time_ms": service.response_time_ms,
                    "consecutive_failures": service.consecutive_failures,
                    "error_message": service.error_message
                }
                for name, service in self._services.items()
            },
            "timestamp": time.time()
        }