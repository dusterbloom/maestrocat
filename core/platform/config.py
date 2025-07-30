"""
Unified Configuration System

Provides a unified configuration system that supports platform-specific sections
while maintaining backward compatibility with existing configuration files.
This system automatically merges base configuration with platform-specific
overrides based on the detected or selected platform.
"""

import logging
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, field
from pathlib import Path
import yaml
import os

from .strategy import PlatformType
from .detector import PlatformDetector

logger = logging.getLogger(__name__)


@dataclass
class UnifiedVADConfig:
    """Voice Activity Detection configuration"""
    energy_threshold: float = 0.5
    min_speech_ms: int = 200
    pause_ms: int = 600


@dataclass
class UnifiedSTTConfig:
    """Speech-to-Text configuration with platform support"""
    # Base settings
    language: str = "en"
    translate: bool = False
    
    # Platform-specific settings (will be populated based on platform)
    service: str = "auto"  # "whisperlive", "mlx_whisper", "whispercpp", "lightning_whisper_mlx", "auto"
    host: str = "localhost"
    port: int = 9090
    model: str = "small"
    model_size: str = "base"  # For MLX/Whisper.cpp
    sample_rate: int = 16000
    use_vad: bool = False
    vad_threshold: float = 0.5
    
    # Lightning Whisper MLX specific settings
    compute_type: str = "float16"  # float16, int8, int4
    batch_size: int = 1
    beam_size: int = 1
    
    # Streaming STT specific settings
    channels: int = 1
    block_size: int = 512
    max_latency_ms: int = 200
    preload_model: bool = True  # Pre-load model during startup for instant transcription


@dataclass
class UnifiedLLMConfig:
    """Large Language Model configuration"""
    base_url: str = "http://localhost:11434"
    model: str = "llama3.2:3b"
    temperature: float = 0.7
    max_tokens: int = 150
    top_p: float = 0.9
    top_k: int = 40
    system_prompt: str = "You are MaestroCat, a helpful AI voice assistant."


@dataclass
class UnifiedTTSConfig:
    """Text-to-Speech configuration with platform support"""
    # Base settings
    voice: str = "af_bella" 
    speed: float = 1.0
    
    # Platform-specific settings (will be populated based on platform)
    service: str = "auto"  # "kokoro", "macos", "pyttsx3", "native_kokoro", "auto"
    base_url: str = "http://localhost:5000"
    sample_rate: int = 24000
    
    # macOS TTS specific
    rate: int = 180
    volume: float = 0.9
    voice_id: Optional[str] = None


@dataclass
class UnifiedInterruptionConfig:
    """Interruption handling configuration"""
    threshold: float = 0.2
    ack_delay: float = 0.05


@dataclass
class UnifiedDevelopmentConfig:
    """Development configuration"""
    log_level: str = "INFO"
    debug_ui: bool = True
    debug_port: int = 8080
    websocket_port: int = 8765


@dataclass
class PlatformSelectionConfig:
    """Platform selection configuration"""
    auto_detect: bool = True
    preferred: Optional[str] = None
    fallbacks: Dict[str, list] = field(default_factory=dict)


class UnifiedMaestroCatConfig:
    """
    Unified configuration system that supports platform-specific sections.
    
    This configuration system:
    1. Loads base configuration applicable to all platforms
    2. Detects the current platform (or uses override)
    3. Merges platform-specific configuration sections
    4. Provides a unified interface for all components
    5. Maintains backward compatibility with existing configs
    """
    
    def __init__(self, 
                 config_dict: Dict[str, Any], 
                 platform_type: Optional[PlatformType] = None,
                 auto_detect_platform: bool = True):
        """
        Initialize unified configuration.
        
        Args:
            config_dict: Raw configuration dictionary
            platform_type: Force specific platform type (optional)
            auto_detect_platform: Whether to auto-detect platform if not specified
        """
        self.raw_config = config_dict
        self._platform_type = platform_type
        
        # Detect platform if not specified
        if platform_type is None and auto_detect_platform:
            platform_info = PlatformDetector.detect_full_platform_info()
            self._platform_type = PlatformDetector.auto_select_strategy_type(platform_info)
        
        # Load base configuration
        self.vad = UnifiedVADConfig(**config_dict.get("vad", {}))
        self.interruption = UnifiedInterruptionConfig(**config_dict.get("interruption", {}))
        self.modules = config_dict.get("modules", {})
        self.development = UnifiedDevelopmentConfig(**config_dict.get("development", {}))
        self.platform_selection = PlatformSelectionConfig(**config_dict.get("platform", {}))
        
        # Load language settings
        self.language = config_dict.get("language", "en")
        self.language_config = config_dict.get("language_config", {})
        
        # Check for platform preference override
        if (self.platform_selection.preferred and 
            self.platform_selection.auto_detect and 
            self._platform_type is None):
            try:
                self._platform_type = PlatformType(self.platform_selection.preferred)
                logger.info(f"Using preferred platform from config: {self._platform_type.value}")
            except ValueError:
                logger.warning(f"Invalid preferred platform in config: {self.platform_selection.preferred}")
        
        # Merge platform-specific configuration
        self._merge_platform_config()
        
        # Store additional sections for backward compatibility
        self.macos = config_dict.get("macos", {})
        self.production = config_dict.get("production", {})
        self.advanced = config_dict.get("advanced", {})
    
    @property
    def platform_type(self) -> Optional[PlatformType]:
        """Get the current platform type"""
        return self._platform_type
    
    def _merge_platform_config(self):
        """Merge platform-specific configuration with base configuration"""
        if not self._platform_type:
            logger.warning("No platform type specified, using base configuration only")
            # Use base configuration as fallback
            self.stt = UnifiedSTTConfig(**self.raw_config.get("stt", {}))
            self.llm = UnifiedLLMConfig(**self.raw_config.get("llm", {}))
            self.tts = UnifiedTTSConfig(**self.raw_config.get("tts", {}))
            return
        
        platforms_config = self.raw_config.get("platforms", {})
        platform_key = self._platform_type.value
        
        # Handle platform inheritance (e.g., WSL extends Docker)
        platform_config = self._resolve_platform_inheritance(platforms_config, platform_key)
        
        if not platform_config:
            logger.warning(f"No platform-specific config found for {platform_key}, using base config")
            # Use base configuration as fallback
            self.stt = UnifiedSTTConfig(**self.raw_config.get("stt", {}))
            self.llm = UnifiedLLMConfig(**self.raw_config.get("llm", {}))
            self.tts = UnifiedTTSConfig(**self.raw_config.get("tts", {}))
            return
        
        # Merge base config with platform-specific config
        base_stt = self.raw_config.get("stt", {})
        base_llm = self.raw_config.get("llm", {})
        base_tts = self.raw_config.get("tts", {})
        
        platform_stt = platform_config.get("stt", {})
        platform_llm = platform_config.get("llm", {})
        platform_tts = platform_config.get("tts", {})
        
        # Merge configurations (platform-specific overrides base)
        merged_stt = {**base_stt, **platform_stt}
        merged_llm = {**base_llm, **platform_llm}
        merged_tts = {**base_tts, **platform_tts}
        
        # Apply language settings from top-level config if not overridden
        if 'language' not in merged_stt and hasattr(self, 'language'):
            # Get STT language from language_config or use the global language
            lang_settings = self.language_config.get(self.language, {})
            merged_stt['language'] = lang_settings.get('stt_language', self.language)
        
        # Apply intelligent model selection based on platform capabilities
        self._apply_intelligent_model_selection(merged_llm, platform_config)
        
        # Clean platform-specific keys that shouldn't be passed to config classes
        self._clean_platform_specific_keys(merged_tts)
        
        # Create final configuration objects
        self.stt = UnifiedSTTConfig(**merged_stt)
        self.llm = UnifiedLLMConfig(**merged_llm)
        self.tts = UnifiedTTSConfig(**merged_tts)
        
        # Override VAD settings if platform specifies them
        if "vad" in platform_config:
            platform_vad = {**self.raw_config.get("vad", {}), **platform_config["vad"]}
            self.vad = UnifiedVADConfig(**platform_vad)
        
        logger.info(f"✅ Merged configuration for platform: {platform_key}")
    
    def _resolve_platform_inheritance(self, platforms_config: Dict, platform_key: str) -> Dict[str, Any]:
        """Resolve platform inheritance (e.g., WSL extends Docker)"""
        if platform_key not in platforms_config:
            return {}
        
        platform_config = platforms_config[platform_key].copy()
        
        # Check for inheritance
        extends = platform_config.pop("extends", None)
        if extends and extends in platforms_config:
            logger.info(f"Platform {platform_key} extends {extends}")
            base_config = self._resolve_platform_inheritance(platforms_config, extends)
            
            # Deep merge configurations
            return self._deep_merge_dicts(base_config, platform_config)
        
        return platform_config
    
    def _deep_merge_dicts(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge_dicts(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _apply_intelligent_model_selection(self, llm_config: Dict, platform_config: Dict):
        """Apply intelligent model selection based on platform capabilities"""
        if self._platform_type == PlatformType.DOCKER:
            # Select model based on GPU availability
            platform_info = PlatformDetector.detect_full_platform_info()
            if platform_info.capabilities.has_gpu:
                gpu_model = llm_config.get("model_gpu")
                if gpu_model:
                    llm_config["model"] = gpu_model
                    logger.info(f"Selected GPU model: {gpu_model}")
            else:
                cpu_model = llm_config.get("model_cpu")
                if cpu_model:
                    llm_config["model"] = cpu_model
                    logger.info(f"Selected CPU model: {cpu_model}")
            
            # Remove the selection keys to avoid passing them to UnifiedLLMConfig
            llm_config.pop("model_gpu", None)
            llm_config.pop("model_cpu", None)
        
        elif self._platform_type == PlatformType.MACOS_NATIVE:
            # Select model based on Apple Silicon generation
            platform_info = PlatformDetector.detect_full_platform_info()
            
            # Detect Apple Silicon generation (simplified heuristic)
            import platform as py_platform
            if py_platform.processor() == "arm":
                # Try to detect specific chip generation
                try:
                    import subprocess
                    result = subprocess.run(
                        ["system_profiler", "SPHardwareDataType"], 
                        capture_output=True, text=True, timeout=5
                    )
                    if "M3" in result.stdout:
                        m3_model = llm_config.get("model_m3")
                        if m3_model:
                            llm_config["model"] = m3_model
                            logger.info(f"Selected M3 model: {m3_model}")
                    elif "M2" in result.stdout:
                        m2_model = llm_config.get("model_m2") 
                        if m2_model:
                            llm_config["model"] = m2_model
                            logger.info(f"Selected M2 model: {m2_model}")
                    elif "M1" in result.stdout:
                        m1_model = llm_config.get("model_m1")
                        if m1_model:
                            llm_config["model"] = m1_model
                            logger.info(f"Selected M1 model: {m1_model}")
                except Exception:
                    pass  # Fall back to default model
            
            # Remove the selection keys to avoid passing them to UnifiedLLMConfig
            llm_config.pop("model_m1", None)
            llm_config.pop("model_m2", None)
            llm_config.pop("model_m3", None)
    
    def _clean_platform_specific_keys(self, config: Dict):
        """Remove platform-specific keys that shouldn't be passed to config classes"""
        # Remove TTS-specific platform keys
        config.pop("fallback", None)
        config.pop("tts_alternatives", None)
    
    @classmethod
    def from_file(cls, 
                  file_path: Union[str, Path], 
                  platform_type: Optional[PlatformType] = None,
                  auto_detect_platform: bool = True) -> "UnifiedMaestroCatConfig":
        """
        Load unified configuration from YAML file.
        
        Args:
            file_path: Path to configuration file
            platform_type: Force specific platform type (optional)
            auto_detect_platform: Whether to auto-detect platform if not specified
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        
        logger.info(f"Loading configuration from: {file_path}")
        
        with open(file_path, "r") as f:
            config_dict = yaml.safe_load(f)
        
        return cls(config_dict, platform_type, auto_detect_platform)
    
    @classmethod
    def from_legacy_file(cls, 
                        file_path: Union[str, Path],
                        platform_type: Optional[PlatformType] = None) -> "UnifiedMaestroCatConfig":
        """
        Load configuration from legacy format files (maestrocat.yaml, maestrocat_macos.yaml).
        
        This method provides backward compatibility with existing configuration files.
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        
        logger.info(f"Loading legacy configuration from: {file_path}")
        
        with open(file_path, "r") as f:
            config_dict = yaml.safe_load(f)
        
        # Infer platform type from filename if not specified
        if platform_type is None:
            if "macos" in file_path.name:
                platform_type = PlatformType.MACOS_NATIVE
            else:
                platform_type = PlatformType.DOCKER
        
        logger.info(f"Inferred platform type from legacy config: {platform_type.value}")
        
        return cls(config_dict, platform_type, auto_detect_platform=False)
    
    @classmethod
    def auto_load(cls, 
                  preferred_path: Optional[Union[str, Path]] = None,
                  platform_type: Optional[PlatformType] = None) -> "UnifiedMaestroCatConfig":
        """
        Automatically load the best available configuration file.
        
        Search order:
        1. Specified preferred_path
        2. maestrocat_unified.yaml (new unified format)
        3. Platform-specific legacy files based on detection
        4. Generic maestrocat.yaml as fallback
        """
        search_paths = []
        
        # Add preferred path if specified
        if preferred_path:
            search_paths.append(Path(preferred_path))
        
        # Add unified config
        search_paths.append(Path("config/maestrocat_unified.yaml"))
        
        # Add platform-specific legacy configs
        if platform_type is None:
            platform_info = PlatformDetector.detect_full_platform_info()
            detected_platform = PlatformDetector.auto_select_strategy_type(platform_info)
        else:
            detected_platform = platform_type
        
        if detected_platform == PlatformType.MACOS_NATIVE:
            search_paths.extend([
                Path("config/maestrocat_macos.yaml"),
                Path("config/maestrocat.yaml")
            ])
        else:
            search_paths.extend([
                Path("config/maestrocat.yaml"),
                Path("config/maestrocat_macos.yaml")  # Fallback
            ])
        
        # Try each path
        for path in search_paths:
            if path.exists():
                logger.info(f"Auto-selected configuration file: {path}")
                
                # Determine if this is unified or legacy format
                if "unified" in path.name:
                    return cls.from_file(path, platform_type)
                else:
                    return cls.from_legacy_file(path, platform_type)
        
        # No config found, create minimal default
        logger.warning("No configuration file found, using defaults")
        return cls({}, platform_type)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration back to dictionary format"""
        return {
            "vad": {
                "energy_threshold": self.vad.energy_threshold,
                "min_speech_ms": self.vad.min_speech_ms,
                "pause_ms": self.vad.pause_ms
            },
            "stt": {
                "service": self.stt.service,
                "host": self.stt.host,
                "port": self.stt.port,
                "language": self.stt.language,
                "translate": self.stt.translate,
                "model": self.stt.model,
                "model_size": self.stt.model_size,
                "sample_rate": self.stt.sample_rate,
                "use_vad": self.stt.use_vad
            },
            "llm": {
                "base_url": self.llm.base_url,
                "model": self.llm.model,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
                "top_p": self.llm.top_p,
                "top_k": self.llm.top_k,
                "system_prompt": self.llm.system_prompt
            },
            "tts": {
                "service": self.tts.service,
                "base_url": self.tts.base_url,
                "voice": self.tts.voice,
                "speed": self.tts.speed,
                "sample_rate": self.tts.sample_rate,
                "rate": self.tts.rate,
                "volume": self.tts.volume
            },
            "interruption": {
                "threshold": self.interruption.threshold,
                "ack_delay": self.interruption.ack_delay
            },
            "modules": self.modules,
            "development": {
                "log_level": self.development.log_level,
                "debug_ui": self.development.debug_ui,
                "debug_port": self.development.debug_port,
                "websocket_port": self.development.websocket_port
            },
            "platform_type": self._platform_type.value if self._platform_type else None,
            "macos": self.macos,
            "production": self.production,
            "advanced": self.advanced
        }
    
    def get_platform_section(self, section_name: str) -> Dict[str, Any]:
        """Get a specific platform configuration section"""
        if not self._platform_type:
            return {}
        
        platforms_config = self.raw_config.get("platforms", {})
        platform_config = platforms_config.get(self._platform_type.value, {})
        
        return platform_config.get(section_name, {})
    
    def __repr__(self) -> str:
        return f"UnifiedMaestroCatConfig(platform={self._platform_type.value if self._platform_type else 'auto'})"