"""
Service Factory

Provides a unified interface for creating platform strategies and managing
the platform abstraction system. Handles automatic platform detection,
strategy selection, and provides fallback mechanisms.
"""

import logging
from typing import Optional, Type, Dict, Any

from .strategy import PlatformStrategy, PlatformType
from .detector import PlatformDetector
from .docker_strategy import DockerPlatformStrategy  
from .macos_strategy import MacOSPlatformStrategy

logger = logging.getLogger(__name__)


class ServiceFactory:
    """
    Factory for creating platform strategies and managing platform abstraction.
    
    Provides:
    - Automatic platform detection and strategy selection
    - Manual platform override capabilities
    - Fallback strategy selection
    - Strategy registration for extensibility
    """
    
    # Registry of available platform strategies
    _strategies: Dict[PlatformType, Type[PlatformStrategy]] = {
        PlatformType.DOCKER: DockerPlatformStrategy,
        PlatformType.MACOS_NATIVE: MacOSPlatformStrategy,
        # Add more strategies here as they're implemented
        # PlatformType.LINUX_NATIVE: LinuxNativePlatformStrategy,
        # PlatformType.WINDOWS: WindowsPlatformStrategy,
    }
    
    @classmethod
    def register_strategy(cls, platform_type: PlatformType, strategy_class: Type[PlatformStrategy]):
        """Register a new platform strategy"""
        cls._strategies[platform_type] = strategy_class
        logger.info(f"Registered platform strategy: {platform_type.value} -> {strategy_class.__name__}")
    
    @classmethod
    def get_available_strategies(cls) -> Dict[PlatformType, Type[PlatformStrategy]]:
        """Get all available platform strategies"""
        return cls._strategies.copy()
    
    @classmethod
    def auto_create_strategy(cls, config: Any, platform_override: Optional[PlatformType] = None) -> PlatformStrategy:
        """
        Automatically detect platform and create the best strategy.
        
        Args:
            config: Configuration object
            platform_override: Force specific platform type (optional)
            
        Returns:
            Configured platform strategy instance
        """
        # Detect platform capabilities
        platform_info = PlatformDetector.detect_full_platform_info()
        
        # Determine strategy type
        if platform_override:
            strategy_type = platform_override
            logger.info(f"Using override platform strategy: {strategy_type.value}")
        else:
            strategy_type = PlatformDetector.auto_select_strategy_type(platform_info)
            logger.info(f"Auto-selected platform strategy: {strategy_type.value}")
        
        # Create strategy
        return cls.create_strategy(strategy_type, config)
    
    @classmethod
    def create_strategy(cls, platform_type: PlatformType, config: Any) -> PlatformStrategy:
        """
        Create a platform strategy of the specified type.
        
        Args:
            platform_type: The platform type to create
            config: Configuration object
            
        Returns:
            Configured platform strategy instance
            
        Raises:
            ValueError: If platform type is not supported
        """
        if platform_type not in cls._strategies:
            available = list(cls._strategies.keys())
            raise ValueError(
                f"Unsupported platform type: {platform_type}. "
                f"Available strategies: {[p.value for p in available]}"
            )
        
        strategy_class = cls._strategies[platform_type]
        
        logger.info(f"Creating {strategy_class.__name__} for platform: {platform_type.value}")
        
        try:
            strategy = strategy_class(config)
            logger.info(f"✅ Created platform strategy: {strategy_class.__name__}")
            return strategy
        except Exception as e:
            logger.error(f"❌ Failed to create platform strategy {strategy_class.__name__}: {e}")
            
            # Try fallback strategy
            fallback_strategy = cls._get_fallback_strategy(platform_type, config)
            if fallback_strategy:
                logger.warning(f"Using fallback strategy: {type(fallback_strategy).__name__}")
                return fallback_strategy
            else:
                raise
    
    @classmethod
    def _get_fallback_strategy(cls, failed_platform: PlatformType, config: Any) -> Optional[PlatformStrategy]:
        """Get a fallback strategy when the preferred strategy fails"""
        # Define fallback hierarchy
        fallback_map = {
            PlatformType.MACOS_NATIVE: [PlatformType.DOCKER],
            PlatformType.DOCKER: [PlatformType.MACOS_NATIVE],  # If on macOS
            PlatformType.WSL: [PlatformType.DOCKER],
            PlatformType.WINDOWS: [PlatformType.DOCKER],
        }
        
        fallbacks = fallback_map.get(failed_platform, [])
        
        for fallback_type in fallbacks:
            if fallback_type in cls._strategies:
                try:
                    strategy_class = cls._strategies[fallback_type]
                    logger.info(f"Attempting fallback to {strategy_class.__name__}")
                    return strategy_class(config)
                except Exception as e:
                    logger.warning(f"Fallback {strategy_class.__name__} also failed: {e}")
                    continue
        
        logger.error("No fallback strategies available")
        return None
    
    @classmethod
    def create_from_config_hint(cls, config: Any) -> PlatformStrategy:
        """
        Create strategy based on configuration hints.
        
        Looks for platform hints in the configuration and uses them
        to guide strategy selection.
        """
        # Check if config specifies a preferred platform
        platform_hint = None
        
        # Look for platform-specific sections in config
        if hasattr(config, 'platform'):
            platform_hint_str = getattr(config.platform, 'preferred', None)
            if platform_hint_str:
                try:
                    platform_hint = PlatformType(platform_hint_str)
                except ValueError:
                    logger.warning(f"Invalid platform hint in config: {platform_hint_str}")
        
        # Check for service-specific hints
        if platform_hint is None:
            # If config has Docker-specific services, prefer Docker
            if (hasattr(config, 'stt') and 
                getattr(config.stt, 'host', None) == 'localhost' and
                getattr(config.stt, 'port', None) == 9090):
                platform_hint = PlatformType.DOCKER
            
            # If config has macOS-specific settings, prefer macOS native
            elif hasattr(config, 'macos'):
                platform_hint = PlatformType.MACOS_NATIVE
        
        return cls.auto_create_strategy(config, platform_hint)
    
    @classmethod
    def validate_strategy_compatibility(cls, strategy: PlatformStrategy) -> tuple[bool, list[str]]:
        """
        Validate that a strategy is compatible with the current environment.
        
        Returns:
            Tuple of (is_compatible, list_of_issues)
        """
        issues = []
        
        try:
            # Check basic platform info
            platform_info = strategy.platform_info
            
            # Check if the strategy's platform matches detected platform
            detected_info = PlatformDetector.detect_full_platform_info()
            
            if strategy.platform_info.platform_type == PlatformType.DOCKER:
                if not detected_info.capabilities.docker_available:
                    issues.append("Docker strategy selected but Docker is not available")
            
            elif strategy.platform_info.platform_type == PlatformType.MACOS_NATIVE:
                if detected_info.platform_type != PlatformType.MACOS_NATIVE:
                    issues.append("macOS native strategy selected but not running on macOS")
                
                # Check for native service requirements
                required_services = {"ollama"}
                available_services = set(detected_info.capabilities.native_services)
                missing_services = required_services - available_services
                
                if missing_services:
                    issues.append(f"Missing required native services: {missing_services}")
        
        except Exception as e:
            issues.append(f"Error validating strategy compatibility: {e}")
        
        return len(issues) == 0, issues
    
    @classmethod
    def get_strategy_recommendations(cls, config: Any) -> Dict[str, Any]:
        """
        Get recommendations for the best platform strategy based on current environment.
        
        Returns:
            Dictionary with recommendations and reasoning
        """
        platform_info = PlatformDetector.detect_full_platform_info()
        
        recommendations = {
            "detected_platform": platform_info.platform_type.value,
            "description": platform_info.description,
            "capabilities": {
                "has_gpu": platform_info.capabilities.has_gpu,
                "supports_metal": platform_info.capabilities.supports_metal,
                "supports_mlx": platform_info.capabilities.supports_mlx,
                "docker_available": platform_info.capabilities.docker_available,
                "native_services": platform_info.capabilities.native_services
            },
            "recommended_strategy": None,
            "reasoning": [],
            "alternatives": [],
            "performance_notes": []
        }
        
        # Generate recommendations
        auto_selected = PlatformDetector.auto_select_strategy_type(platform_info)
        recommendations["recommended_strategy"] = auto_selected.value
        
        if auto_selected == PlatformType.MACOS_NATIVE:
            recommendations["reasoning"].append("macOS detected with native services available")
            if platform_info.capabilities.supports_mlx:
                recommendations["reasoning"].append("Apple Silicon with MLX acceleration available")
                recommendations["performance_notes"].append("WhisperCpp native provides best STT performance")
            
            if platform_info.capabilities.docker_available:
                recommendations["alternatives"].append({
                    "strategy": PlatformType.DOCKER.value,
                    "note": "Docker services available as alternative"
                })
        
        elif auto_selected == PlatformType.DOCKER:
            recommendations["reasoning"].append("Docker services detected and available")
            if platform_info.capabilities.has_gpu:
                recommendations["reasoning"].append("GPU acceleration available for Docker services")
                recommendations["performance_notes"].append("GPU-accelerated services provide best performance")
            else:
                recommendations["performance_notes"].append("CPU-only services - consider smaller models")
        
        return recommendations