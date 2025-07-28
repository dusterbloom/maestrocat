"""
Platform Strategy Interface

Defines the abstract interface that all platform strategies must implement.
This enables clean separation of platform-specific logic while maintaining
a consistent interface for the unified agent.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from pipecat.transports.network.fastapi_websocket import FastAPIWebsocketParams
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext


class PlatformType(Enum):
    """Supported platform types"""
    DOCKER = "docker"
    MACOS_NATIVE = "macos_native"
    LINUX_NATIVE = "linux_native"
    WSL = "wsl"
    WINDOWS = "windows"


@dataclass
class PlatformCapabilities:
    """Platform capabilities and constraints"""
    has_gpu: bool = False
    supports_metal: bool = False
    supports_mlx: bool = False
    docker_available: bool = False
    native_services: List[str] = None
    
    def __post_init__(self):
        if self.native_services is None:
            self.native_services = []


@dataclass 
class PlatformInfo:
    """Complete platform information"""
    platform_type: PlatformType
    capabilities: PlatformCapabilities
    description: str
    recommended_models: Dict[str, str] = None
    
    def __post_init__(self):
        if self.recommended_models is None:
            self.recommended_models = {}


@dataclass
class ServiceSpecs:
    """Service specifications for a platform strategy"""
    stt_service: str
    llm_service: str
    tts_service: str
    transport_class: str = "FastAPIWebsocketTransport"
    additional_processors: List[str] = None
    
    def __post_init__(self):
        if self.additional_processors is None:
            self.additional_processors = []


class PlatformStrategy(ABC):
    """
    Abstract base class for platform strategies.
    
    Each platform strategy encapsulates all platform-specific logic including:
    - Service creation and configuration
    - Dependency checking and validation
    - Platform-specific optimizations
    - Error handling and fallbacks
    """
    
    def __init__(self, config: Any):
        self.config = config
        self._services_created = False
        self._dependencies_checked = False
    
    @property
    @abstractmethod
    def platform_info(self) -> PlatformInfo:
        """Get information about this platform"""
        pass
    
    @property
    @abstractmethod
    def service_specs(self) -> ServiceSpecs:
        """Get service specifications for this platform"""
        pass
    
    @abstractmethod
    async def check_dependencies(self) -> Tuple[bool, List[str]]:
        """
        Check if all required dependencies are available.
        
        Returns:
            Tuple of (success: bool, missing_dependencies: List[str])
        """
        pass
    
    @abstractmethod
    async def setup_services(self) -> bool:
        """
        Set up any required services (e.g., start Docker containers).
        
        Returns:
            True if setup successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def create_stt_service(self, event_emitter=None):
        """Create and configure the STT service for this platform"""
        pass
    
    @abstractmethod
    async def create_llm_service(self, event_emitter=None):
        """Create and configure the LLM service for this platform"""
        pass
    
    @abstractmethod
    async def create_tts_service(self, event_emitter=None):
        """Create and configure the TTS service for this platform"""
        pass
    
    @abstractmethod
    def create_transport_params(self) -> FastAPIWebsocketParams:
        """Create transport parameters optimized for this platform"""
        pass
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Get the system prompt, potentially customized for platform performance"""
        pass
    
    async def apply_platform_optimizations(self) -> Dict[str, Any]:
        """
        Apply platform-specific optimizations.
        Default implementation returns empty dict.
        
        Returns:
            Dictionary of applied optimizations for logging/debugging
        """
        return {}
    
    async def cleanup(self):
        """
        Clean up platform-specific resources.
        Default implementation does nothing.
        """
        pass
    
    def get_health_info(self) -> Dict[str, Any]:
        """
        Get platform-specific health information.
        Default implementation returns basic info.
        """
        return {
            "platform_type": self.platform_info.platform_type.value,
            "services_created": self._services_created,
            "dependencies_checked": self._dependencies_checked,
            "capabilities": {
                "has_gpu": self.platform_info.capabilities.has_gpu,
                "supports_metal": self.platform_info.capabilities.supports_metal,
                "supports_mlx": self.platform_info.capabilities.supports_mlx,
                "docker_available": self.platform_info.capabilities.docker_available,
                "native_services": self.platform_info.capabilities.native_services
            }
        }
    
    def get_debug_info(self) -> Dict[str, Any]:
        """Get platform-specific debug information"""
        return {
            "platform_info": self.platform_info,
            "service_specs": self.service_specs,
            "config_section": getattr(self.config, self.platform_info.platform_type.value, {}),
            "health": self.get_health_info()
        }