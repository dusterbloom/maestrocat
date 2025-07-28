# Service Registry and Discovery
"""
Service registry for tracking service availability and implementing fallback strategies.
Provides centralized service discovery, load balancing, and failover capabilities.
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
import random

logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """Types of services in MaestroCat"""
    STT = "stt"              # Speech-to-Text
    LLM = "llm"              # Language Model
    TTS = "tts"              # Text-to-Speech
    AUDIO_INPUT = "audio_input"   # Audio input transport
    AUDIO_OUTPUT = "audio_output" # Audio output transport
    CUSTOM = "custom"        # Custom service type


class ServiceStatus(Enum):
    """Service availability status"""
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    MAINTENANCE = "maintenance"


@dataclass
class ServiceEndpoint:
    """Service endpoint configuration"""
    protocol: str           # http, ws, grpc, etc.
    host: str
    port: int
    path: str = ""
    secure: bool = False
    
    @property
    def url(self) -> str:
        """Get full URL for this endpoint"""
        scheme = f"{self.protocol}s" if self.secure else self.protocol
        path = f"/{self.path.lstrip('/')}" if self.path else ""
        return f"{scheme}://{self.host}:{self.port}{path}"


@dataclass
class ServiceInfo:
    """Information about a registered service"""
    service_id: str
    service_type: ServiceType
    name: str
    version: str
    endpoints: List[ServiceEndpoint]
    status: ServiceStatus = ServiceStatus.AVAILABLE
    priority: int = 0                    # Higher priority = preferred
    weight: int = 100                    # For load balancing (0-100)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    health_check_url: Optional[str] = None
    
    # Runtime tracking
    last_seen: float = field(default_factory=time.time)
    request_count: int = 0
    error_count: int = 0
    average_response_time: float = 0.0
    
    @property
    def primary_endpoint(self) -> ServiceEndpoint:
        """Get primary endpoint for this service"""
        return self.endpoints[0] if self.endpoints else None
        
    @property
    def error_rate(self) -> float:
        """Calculate error rate percentage"""
        if self.request_count == 0:
            return 0.0
        return (self.error_count / self.request_count) * 100
        
    @property
    def is_healthy(self) -> bool:
        """Check if service is considered healthy"""
        return (
            self.status in (ServiceStatus.AVAILABLE, ServiceStatus.DEGRADED) and
            self.error_rate < 50.0  # Less than 50% error rate
        )


class LoadBalancingStrategy(Enum):
    """Load balancing strategies"""
    ROUND_ROBIN = "round_robin"
    WEIGHTED_RANDOM = "weighted_random"
    LEAST_CONNECTIONS = "least_connections"
    FASTEST_RESPONSE = "fastest_response"
    PRIORITY_FIRST = "priority_first"


class ServiceRegistry:
    """
    Central service registry for managing service discovery and failover.
    
    Features:
    - Service registration and discovery
    - Health-based service filtering
    - Multiple load balancing strategies
    - Automatic failover and circuit breaking integration
    - Service capability matching
    """
    
    def __init__(
        self,
        event_emitter = None,
        default_strategy: LoadBalancingStrategy = LoadBalancingStrategy.PRIORITY_FIRST,
        service_timeout: float = 30.0
    ):
        self._event_emitter = event_emitter
        self.default_strategy = default_strategy
        self.service_timeout = service_timeout
        
        # Service storage
        self._services: Dict[str, ServiceInfo] = {}
        self._services_by_type: Dict[ServiceType, List[str]] = {}
        
        # Load balancing state
        self._round_robin_counters: Dict[ServiceType, int] = {}
        
        # Fallback configurations
        self._fallback_chains: Dict[ServiceType, List[str]] = {}
        self._service_factories: Dict[str, Callable] = {}
        
    def register_service(
        self,
        service_info: ServiceInfo,
        replace_existing: bool = True
    ) -> bool:
        """
        Register a service in the registry.
        
        Args:
            service_info: Service information
            replace_existing: Whether to replace existing service with same ID
            
        Returns:
            True if registered successfully
        """
        service_id = service_info.service_id
        
        # Check if service already exists
        if service_id in self._services and not replace_existing:
            logger.warning(f"Service {service_id} already registered")
            return False
            
        # Register the service
        self._services[service_id] = service_info
        
        # Add to type index
        service_type = service_info.service_type
        if service_type not in self._services_by_type:
            self._services_by_type[service_type] = []
        if service_id not in self._services_by_type[service_type]:
            self._services_by_type[service_type].append(service_id)
            
        # Sort by priority (highest first)
        self._services_by_type[service_type].sort(
            key=lambda sid: self._services[sid].priority,
            reverse=True
        )
        
        logger.info(f"Registered service: {service_id} ({service_type.value})")
        
        # Emit registration event
        asyncio.create_task(self._emit_event("service_registered", {
            "service_id": service_id,
            "service_type": service_type.value,
            "name": service_info.name,
            "endpoints": [ep.url for ep in service_info.endpoints]
        }))
        
        return True
        
    def unregister_service(self, service_id: str) -> bool:
        """Unregister a service from the registry"""
        if service_id not in self._services:
            return False
            
        service_info = self._services[service_id]
        service_type = service_info.service_type
        
        # Remove from storage
        del self._services[service_id]
        
        # Remove from type index
        if service_type in self._services_by_type:
            self._services_by_type[service_type] = [
                sid for sid in self._services_by_type[service_type]
                if sid != service_id
            ]
            
        logger.info(f"Unregistered service: {service_id}")
        
        # Emit unregistration event
        asyncio.create_task(self._emit_event("service_unregistered", {
            "service_id": service_id,
            "service_type": service_type.value
        }))
        
        return True
        
    def get_service(self, service_id: str) -> Optional[ServiceInfo]:
        """Get service information by ID"""
        return self._services.get(service_id)
        
    def get_services_by_type(
        self,
        service_type: ServiceType,
        only_healthy: bool = True,
        capabilities: Optional[Dict[str, Any]] = None
    ) -> List[ServiceInfo]:
        """
        Get all services of a specific type.
        
        Args:
            service_type: Type of service to find
            only_healthy: Only return healthy services
            capabilities: Required service capabilities
            
        Returns:
            List of matching services
        """
        if service_type not in self._services_by_type:
            return []
            
        service_ids = self._services_by_type[service_type]
        services = []
        
        for service_id in service_ids:
            service = self._services.get(service_id)
            if not service:
                continue
                
            # Filter by health
            if only_healthy and not service.is_healthy:
                continue
                
            # Filter by capabilities
            if capabilities:
                if not self._check_capabilities(service, capabilities):
                    continue
                    
            services.append(service)
            
        return services
        
    def discover_service(
        self,
        service_type: ServiceType,
        strategy: Optional[LoadBalancingStrategy] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        exclude_services: Optional[List[str]] = None
    ) -> Optional[ServiceInfo]:
        """
        Discover and select a service using load balancing strategy.
        
        Args:
            service_type: Type of service needed
            strategy: Load balancing strategy to use
            capabilities: Required service capabilities
            exclude_services: Service IDs to exclude from selection
            
        Returns:
            Selected service or None if no suitable service found
        """
        # Get available services
        services = self.get_services_by_type(
            service_type,
            only_healthy=True,
            capabilities=capabilities
        )
        
        # Filter out excluded services
        if exclude_services:
            services = [s for s in services if s.service_id not in exclude_services]
            
        if not services:
            logger.warning(f"No healthy services found for type {service_type.value}")
            return None
            
        # Apply load balancing strategy
        strategy = strategy or self.default_strategy
        selected_service = self._select_service(services, strategy, service_type)
        
        if selected_service:
            # Update request tracking
            selected_service.request_count += 1
            selected_service.last_seen = time.time()
            
            # Emit discovery event
            asyncio.create_task(self._emit_event("service_discovered", {
                "service_id": selected_service.service_id,
                "service_type": service_type.value,
                "strategy": strategy.value
            }))
            
        return selected_service
        
    def _select_service(
        self,
        services: List[ServiceInfo],
        strategy: LoadBalancingStrategy,
        service_type: ServiceType
    ) -> Optional[ServiceInfo]:
        """Select service based on load balancing strategy"""
        if not services:
            return None
            
        if strategy == LoadBalancingStrategy.PRIORITY_FIRST:
            # Services are already sorted by priority
            return services[0]
            
        elif strategy == LoadBalancingStrategy.ROUND_ROBIN:
            if service_type not in self._round_robin_counters:
                self._round_robin_counters[service_type] = 0
            counter = self._round_robin_counters[service_type]
            selected = services[counter % len(services)]
            self._round_robin_counters[service_type] = (counter + 1) % len(services)
            return selected
            
        elif strategy == LoadBalancingStrategy.WEIGHTED_RANDOM:
            # Select based on weights
            total_weight = sum(s.weight for s in services if s.weight > 0)
            if total_weight == 0:
                return random.choice(services)
                
            random_value = random.randint(1, total_weight)
            current_weight = 0
            for service in services:
                current_weight += service.weight
                if current_weight >= random_value:
                    return service
            return services[-1]  # Fallback
            
        elif strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            # Select service with lowest request count
            return min(services, key=lambda s: s.request_count)
            
        elif strategy == LoadBalancingStrategy.FASTEST_RESPONSE:
            # Select service with lowest average response time
            return min(services, key=lambda s: s.average_response_time)
            
        return services[0]  # Default fallback
        
    def _check_capabilities(
        self,
        service: ServiceInfo,
        required_capabilities: Dict[str, Any]
    ) -> bool:
        """Check if service has required capabilities"""
        for key, required_value in required_capabilities.items():
            if key not in service.capabilities:
                return False
                
            service_value = service.capabilities[key]
            
            # Handle different capability types
            if isinstance(required_value, (list, tuple)):
                # Service must support at least one of the required values
                if service_value not in required_value:
                    return False
            elif isinstance(required_value, dict):
                # Nested capability check
                if not isinstance(service_value, dict):
                    return False
                if not self._check_capabilities_dict(service_value, required_value):
                    return False
            else:
                # Direct value match
                if service_value != required_value:
                    return False
                    
        return True
        
    def _check_capabilities_dict(self, service_caps: dict, required_caps: dict) -> bool:
        """Recursively check nested capability dictionaries"""
        for key, required_value in required_caps.items():
            if key not in service_caps:
                return False
            if service_caps[key] != required_value:
                return False
        return True
        
    def set_fallback_chain(
        self,
        service_type: ServiceType,
        service_ids: List[str]
    ):
        """Set fallback chain for a service type"""
        self._fallback_chains[service_type] = service_ids
        logger.info(f"Set fallback chain for {service_type.value}: {service_ids}")
        
    def get_fallback_service(
        self,
        service_type: ServiceType,
        failed_service_id: Optional[str] = None
    ) -> Optional[ServiceInfo]:
        """
        Get fallback service when primary service fails.
        
        Args:
            service_type: Type of service needed
            failed_service_id: ID of service that failed (to exclude)
            
        Returns:
            Fallback service or None
        """
        # Try fallback chain first
        if service_type in self._fallback_chains:
            for service_id in self._fallback_chains[service_type]:
                if service_id == failed_service_id:
                    continue
                service = self.get_service(service_id)
                if service and service.is_healthy:
                    logger.info(f"Using fallback service {service_id} for {service_type.value}")
                    return service
                    
        # Try general service discovery excluding failed service
        exclude_list = [failed_service_id] if failed_service_id else None
        return self.discover_service(
            service_type,
            strategy=LoadBalancingStrategy.PRIORITY_FIRST,
            exclude_services=exclude_list
        )
        
    def update_service_stats(
        self,
        service_id: str,
        response_time_ms: float,
        success: bool = True
    ):
        """Update service performance statistics"""
        service = self.get_service(service_id)
        if not service:
            return
            
        # Update response time (exponential moving average)
        alpha = 0.1  # Smoothing factor
        service.average_response_time = (
            alpha * response_time_ms + 
            (1 - alpha) * service.average_response_time
        )
        
        # Update error count
        if not success:
            service.error_count += 1
            
        service.last_seen = time.time()
        
    def mark_service_unavailable(self, service_id: str, reason: str = ""):
        """Mark a service as temporarily unavailable"""
        service = self.get_service(service_id)
        if service:
            old_status = service.status
            service.status = ServiceStatus.UNAVAILABLE
            
            logger.warning(f"Marked service {service_id} as unavailable: {reason}")
            
            # Emit status change event
            asyncio.create_task(self._emit_event("service_status_changed", {
                "service_id": service_id,
                "old_status": old_status.value,
                "new_status": service.status.value,
                "reason": reason
            }))
            
    def mark_service_available(self, service_id: str):
        """Mark a service as available again"""
        service = self.get_service(service_id)
        if service:
            old_status = service.status
            service.status = ServiceStatus.AVAILABLE
            
            logger.info(f"Marked service {service_id} as available")
            
            # Emit status change event
            asyncio.create_task(self._emit_event("service_status_changed", {
                "service_id": service_id,
                "old_status": old_status.value,
                "new_status": service.status.value
            }))
            
    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit service registry events"""
        if self._event_emitter:
            await self._event_emitter.emit(f"registry_{event_type}", data)
            
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get comprehensive registry statistics"""
        stats_by_type = {}
        for service_type, service_ids in self._services_by_type.items():
            services = [self._services[sid] for sid in service_ids]
            healthy_count = sum(1 for s in services if s.is_healthy)
            
            stats_by_type[service_type.value] = {
                "total": len(services),
                "healthy": healthy_count,
                "unhealthy": len(services) - healthy_count,
                "average_response_time": sum(s.average_response_time for s in services) / len(services) if services else 0,
                "total_requests": sum(s.request_count for s in services),
                "total_errors": sum(s.error_count for s in services)
            }
            
        return {
            "total_services": len(self._services),
            "services_by_type": stats_by_type,
            "timestamp": time.time()
        }