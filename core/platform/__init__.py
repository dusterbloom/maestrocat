"""
MaestroCat Platform Abstraction System

This module provides a unified platform abstraction system that eliminates code duplication
between different platform implementations (Docker, macOS native, etc.) while providing
clean interfaces for adding new platforms.

Key Components:
- PlatformStrategy: Abstract interface for platform-specific implementations
- PlatformDetector: Automatic platform detection and capability assessment
- ServiceFactory: Platform-aware service creation
- MaestroCatAgent: Unified agent using platform strategies
"""

from .strategy import PlatformStrategy, PlatformInfo
from .detector import PlatformDetector
from .factory import ServiceFactory
from .docker_strategy import DockerPlatformStrategy
from .macos_strategy import MacOSPlatformStrategy
from .agent import MaestroCatAgent

__all__ = [
    'PlatformStrategy',
    'PlatformInfo', 
    'PlatformDetector',
    'ServiceFactory',
    'DockerPlatformStrategy',
    'MacOSPlatformStrategy',
    'MaestroCatAgent'
]