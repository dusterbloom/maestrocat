# Reliability Configuration System
"""
Comprehensive configuration system for MaestroCat reliability features.
Provides centralized configuration management for all reliability components.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import yaml
import os

from .circuit_breaker import CircuitBreakerConfig
from .backoff import BackoffConfig, BackoffStrategy
from .error_handler import ErrorLevel, RecoveryStrategy


class ReliabilityProfile(Enum):
    """Predefined reliability profiles"""
    DEVELOPMENT = "development"        # Lenient settings for development
    PRODUCTION = "production"          # Strict settings for production
    HIGH_AVAILABILITY = "high_availability"  # Maximum reliability
    PERFORMANCE = "performance"        # Optimized for performance over reliability


@dataclass
class ServiceReliabilityConfig:
    """Reliability configuration for a single service"""
    # Circuit breaker settings
    circuit_breaker_enabled: bool = True
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_success_threshold: int = 3
    circuit_breaker_timeout: float = 60.0
    circuit_breaker_request_timeout: float = 30.0
    circuit_breaker_health_check_interval: float = 30.0
    
    # Exponential backoff settings
    backoff_enabled: bool = True
    backoff_initial_delay: float = 1.0
    backoff_max_delay: float = 60.0
    backoff_multiplier: float = 2.0
    backoff_jitter: bool = True
    backoff_max_retries: Optional[int] = 3
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    
    # Error handling settings
    error_handler_enabled: bool = True
    error_rate_window: float = 300.0  # 5 minutes
    circuit_break_threshold: int = 10
    
    # Memory guard settings
    memory_guard_enabled: bool = True
    memory_medium_threshold_mb: int = 512
    memory_high_threshold_mb: int = 1024
    memory_critical_threshold_mb: int = 2048
    memory_check_interval: float = 30.0
    
    # Health monitoring settings
    health_monitoring_enabled: bool = True
    health_check_interval: float = 30.0
    health_check_timeout: float = 10.0
    consecutive_failures_threshold: int = 3
    
    # Service-specific settings
    service_specific: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GlobalReliabilityConfig:
    """Global reliability configuration"""
    # Default service configuration
    default_service_config: ServiceReliabilityConfig = field(default_factory=ServiceReliabilityConfig)
    
    # Service-specific overrides
    service_configs: Dict[str, ServiceReliabilityConfig] = field(default_factory=dict)
    
    # Event system settings
    event_buffer_size: int = 1000
    event_emit_as_frames: bool = True
    
    # Service registry settings
    registry_enabled: bool = True
    registry_default_strategy: str = "priority_first"
    registry_service_timeout: float = 30.0
    
    # System monitoring settings
    system_monitoring_enabled: bool = True
    system_memory_threshold_mb: int = 1024
    system_cpu_threshold_percent: float = 80.0
    
    # Logging settings
    reliability_log_level: str = "INFO"
    enable_performance_logging: bool = True
    enable_error_aggregation: bool = True


class ReliabilityConfigManager:
    """
    Manager for reliability configuration with profile support and dynamic updates.
    """
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self._config: Optional[GlobalReliabilityConfig] = None
        self._profiles = self._load_default_profiles()
        
    def _load_default_profiles(self) -> Dict[ReliabilityProfile, GlobalReliabilityConfig]:
        """Load default reliability profiles"""
        profiles = {}
        
        # Development profile - lenient settings
        dev_service_config = ServiceReliabilityConfig(
            circuit_breaker_failure_threshold=10,
            circuit_breaker_timeout=30.0,
            backoff_max_retries=2,
            backoff_max_delay=30.0,
            memory_medium_threshold_mb=1024,
            memory_high_threshold_mb=2048,
            memory_critical_threshold_mb=4096,
            health_check_interval=60.0,
            consecutive_failures_threshold=5
        )
        profiles[ReliabilityProfile.DEVELOPMENT] = GlobalReliabilityConfig(
            default_service_config=dev_service_config,
            reliability_log_level="DEBUG"
        )
        
        # Production profile - balanced settings
        prod_service_config = ServiceReliabilityConfig(
            circuit_breaker_failure_threshold=5,
            circuit_breaker_timeout=60.0,
            backoff_max_retries=3,
            backoff_max_delay=60.0,
            memory_medium_threshold_mb=512,
            memory_high_threshold_mb=1024,
            memory_critical_threshold_mb=2048,
            health_check_interval=30.0,
            consecutive_failures_threshold=3
        )
        profiles[ReliabilityProfile.PRODUCTION] = GlobalReliabilityConfig(
            default_service_config=prod_service_config,
            reliability_log_level="INFO"
        )
        
        # High availability profile - strict settings
        ha_service_config = ServiceReliabilityConfig(
            circuit_breaker_failure_threshold=3,
            circuit_breaker_timeout=30.0,
            circuit_breaker_health_check_interval=15.0,
            backoff_max_retries=5,
            backoff_max_delay=120.0,
            memory_medium_threshold_mb=256,
            memory_high_threshold_mb=512,
            memory_critical_threshold_mb=1024,
            health_check_interval=15.0,
            consecutive_failures_threshold=2
        )
        profiles[ReliabilityProfile.HIGH_AVAILABILITY] = GlobalReliabilityConfig(
            default_service_config=ha_service_config,
            reliability_log_level="WARNING",
            enable_error_aggregation=True
        )
        
        # Performance profile - optimized for speed
        perf_service_config = ServiceReliabilityConfig(
            circuit_breaker_failure_threshold=8,
            circuit_breaker_timeout=120.0,
            backoff_max_retries=1,
            backoff_max_delay=10.0,
            memory_guard_enabled=False,  # Disable for performance
            health_check_interval=120.0,
            consecutive_failures_threshold=10
        )
        profiles[ReliabilityProfile.PERFORMANCE] = GlobalReliabilityConfig(
            default_service_config=perf_service_config,
            reliability_log_level="ERROR",
            enable_performance_logging=False
        )
        
        return profiles
        
    def load_profile(self, profile: ReliabilityProfile) -> GlobalReliabilityConfig:
        """Load a predefined reliability profile"""
        if profile not in self._profiles:
            raise ValueError(f"Unknown reliability profile: {profile}")
            
        self._config = self._profiles[profile]
        return self._config
        
    def load_from_file(self, file_path: str) -> GlobalReliabilityConfig:
        """Load configuration from YAML file"""
        with open(file_path, 'r') as f:
            config_dict = yaml.safe_load(f)
            
        self._config = self._dict_to_config(config_dict)
        return self._config
        
    def load_from_env(self) -> GlobalReliabilityConfig:
        """Load configuration from environment variables"""
        config_dict = {}
        
        # Parse environment variables with MAESTROCAT_RELIABILITY_ prefix
        for key, value in os.environ.items():
            if key.startswith('MAESTROCAT_RELIABILITY_'):
                config_key = key.replace('MAESTROCAT_RELIABILITY_', '').lower()
                
                # Convert string values to appropriate types
                if value.lower() in ('true', 'false'):
                    value = value.lower() == 'true'
                elif value.isdigit():
                    value = int(value)
                elif '.' in value and value.replace('.', '').isdigit():
                    value = float(value)
                    
                config_dict[config_key] = value
                
        self._config = self._dict_to_config(config_dict)
        return self._config
        
    def _dict_to_config(self, config_dict: Dict[str, Any]) -> GlobalReliabilityConfig:
        """Convert dictionary to configuration object"""
        # Extract default service config
        default_service_dict = config_dict.get('default_service', {})
        default_service_config = ServiceReliabilityConfig(**default_service_dict)
        
        # Extract service-specific configs
        service_configs = {}
        services_dict = config_dict.get('services', {})
        for service_name, service_dict in services_dict.items():
            service_configs[service_name] = ServiceReliabilityConfig(**service_dict)
            
        # Create global config
        global_dict = {k: v for k, v in config_dict.items() 
                      if k not in ('default_service', 'services')}
        global_dict['default_service_config'] = default_service_config
        global_dict['service_configs'] = service_configs
        
        return GlobalReliabilityConfig(**global_dict)
        
    def get_config(self) -> GlobalReliabilityConfig:
        """Get current configuration"""
        if self._config is None:
            # Load default production profile
            self._config = self._profiles[ReliabilityProfile.PRODUCTION]
        return self._config
        
    def get_service_config(self, service_name: str) -> ServiceReliabilityConfig:
        """Get configuration for a specific service"""
        config = self.get_config()
        
        if service_name in config.service_configs:
            return config.service_configs[service_name]
        else:
            return config.default_service_config
            
    def get_circuit_breaker_config(self, service_name: str) -> CircuitBreakerConfig:
        """Get circuit breaker configuration for a service"""
        service_config = self.get_service_config(service_name)
        
        return CircuitBreakerConfig(
            failure_threshold=service_config.circuit_breaker_failure_threshold,
            success_threshold=service_config.circuit_breaker_success_threshold,
            timeout=service_config.circuit_breaker_timeout,
            request_timeout=service_config.circuit_breaker_request_timeout,
            health_check_interval=service_config.circuit_breaker_health_check_interval
        )
        
    def get_backoff_config(self, service_name: str) -> BackoffConfig:
        """Get backoff configuration for a service"""
        service_config = self.get_service_config(service_name)
        
        return BackoffConfig(
            initial_delay=service_config.backoff_initial_delay,
            max_delay=service_config.backoff_max_delay,
            multiplier=service_config.backoff_multiplier,
            jitter=service_config.backoff_jitter,
            max_retries=service_config.backoff_max_retries,
            strategy=service_config.backoff_strategy
        )
        
    def update_service_config(
        self,
        service_name: str,
        config_updates: Dict[str, Any]
    ):
        """Update configuration for a specific service"""
        config = self.get_config()
        
        if service_name not in config.service_configs:
            # Create new service config based on default
            config.service_configs[service_name] = ServiceReliabilityConfig(
                **config.default_service_config.__dict__
            )
            
        # Update specific fields
        service_config = config.service_configs[service_name]
        for key, value in config_updates.items():
            if hasattr(service_config, key):
                setattr(service_config, key, value)
                
    def save_to_file(self, file_path: str):
        """Save current configuration to YAML file"""
        if self._config is None:
            raise ValueError("No configuration loaded")
            
        config_dict = self._config_to_dict(self._config)
        
        with open(file_path, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False, indent=2)
            
    def _config_to_dict(self, config: GlobalReliabilityConfig) -> Dict[str, Any]:
        """Convert configuration object to dictionary"""
        config_dict = {}
        
        # Default service config
        default_service = config.default_service_config.__dict__.copy()
        # Convert enum to string
        if 'backoff_strategy' in default_service:
            default_service['backoff_strategy'] = default_service['backoff_strategy'].value
        config_dict['default_service'] = default_service
        
        # Service-specific configs
        services = {}
        for service_name, service_config in config.service_configs.items():
            service_dict = service_config.__dict__.copy()
            if 'backoff_strategy' in service_dict:
                service_dict['backoff_strategy'] = service_dict['backoff_strategy'].value
            services[service_name] = service_dict
        config_dict['services'] = services
        
        # Global settings
        for attr_name in dir(config):
            if not attr_name.startswith('_') and attr_name not in ('default_service_config', 'service_configs'):
                attr_value = getattr(config, attr_name)
                if not callable(attr_value):
                    config_dict[attr_name] = attr_value
                    
        return config_dict
        
    def validate_config(self) -> List[str]:
        """Validate current configuration and return list of issues"""
        issues = []
        config = self.get_config()
        
        # Validate default service config
        issues.extend(self._validate_service_config("default", config.default_service_config))
        
        # Validate service-specific configs
        for service_name, service_config in config.service_configs.items():
            issues.extend(self._validate_service_config(service_name, service_config))
            
        return issues
        
    def _validate_service_config(
        self,
        service_name: str,
        config: ServiceReliabilityConfig
    ) -> List[str]:
        """Validate a service configuration"""
        issues = []
        
        # Circuit breaker validation
        if config.circuit_breaker_failure_threshold <= 0:
            issues.append(f"{service_name}: circuit_breaker_failure_threshold must be > 0")
            
        if config.circuit_breaker_success_threshold <= 0:
            issues.append(f"{service_name}: circuit_breaker_success_threshold must be > 0")
            
        if config.circuit_breaker_timeout <= 0:
            issues.append(f"{service_name}: circuit_breaker_timeout must be > 0")
            
        # Backoff validation
        if config.backoff_initial_delay <= 0:
            issues.append(f"{service_name}: backoff_initial_delay must be > 0")
            
        if config.backoff_max_delay < config.backoff_initial_delay:
            issues.append(f"{service_name}: backoff_max_delay must be >= backoff_initial_delay")
            
        if config.backoff_multiplier <= 1.0:
            issues.append(f"{service_name}: backoff_multiplier must be > 1.0")
            
        # Memory thresholds validation
        if config.memory_medium_threshold_mb <= 0:
            issues.append(f"{service_name}: memory_medium_threshold_mb must be > 0")
            
        if config.memory_high_threshold_mb <= config.memory_medium_threshold_mb:
            issues.append(f"{service_name}: memory_high_threshold_mb must be > memory_medium_threshold_mb")
            
        if config.memory_critical_threshold_mb <= config.memory_high_threshold_mb:
            issues.append(f"{service_name}: memory_critical_threshold_mb must be > memory_high_threshold_mb")
            
        return issues


# Global config manager instance
_config_manager = ReliabilityConfigManager()


def get_config_manager() -> ReliabilityConfigManager:
    """Get the global configuration manager instance"""
    return _config_manager


def load_reliability_config(
    profile: Optional[ReliabilityProfile] = None,
    config_file: Optional[str] = None,
    from_env: bool = False
) -> GlobalReliabilityConfig:
    """
    Load reliability configuration using various sources.
    
    Args:
        profile: Predefined profile to load
        config_file: Path to YAML configuration file
        from_env: Load from environment variables
        
    Returns:
        Loaded configuration
    """
    manager = get_config_manager()
    
    if config_file:
        return manager.load_from_file(config_file)
    elif from_env:
        return manager.load_from_env()
    elif profile:
        return manager.load_profile(profile)
    else:
        # Default to production profile
        return manager.load_profile(ReliabilityProfile.PRODUCTION)