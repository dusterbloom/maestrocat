"""
Migration and Backward Compatibility Support

Provides utilities for migrating from the old platform-specific implementations
to the new unified platform abstraction system while maintaining backward
compatibility during the transition period.
"""

import logging
import warnings
from pathlib import Path
from typing import Optional, Dict, Any, Union
import importlib.util

from .config import UnifiedMaestroCatConfig
from .agent import MaestroCatAgent
from .strategy import PlatformType

logger = logging.getLogger(__name__)


class LegacyAgentWrapper:
    """
    Wrapper that provides backward compatibility for legacy agent classes.
    
    This allows existing code that imports LocalMaestroCatAgent or MacOSMaestroCatAgent
    to continue working without modification while transparently using the new
    platform abstraction system.
    """
    
    def __init__(self, legacy_agent_name: str, config_file: str = None):
        """
        Initialize legacy agent wrapper.
        
        Args:
            legacy_agent_name: Name of the legacy agent class being wrapped
            config_file: Path to configuration file
        """
        self.legacy_agent_name = legacy_agent_name
        self._issue_deprecation_warning()
        
        # Determine platform type based on legacy agent name
        if "macos" in legacy_agent_name.lower():
            platform_type = PlatformType.MACOS_NATIVE
            default_config = "config/maestrocat_macos.yaml"
        else:
            platform_type = PlatformType.DOCKER
            default_config = "config/maestrocat.yaml"
        
        # Load configuration using legacy format
        if config_file:
            config = UnifiedMaestroCatConfig.from_legacy_file(config_file, platform_type)
        else:
            config = UnifiedMaestroCatConfig.from_legacy_file(default_config, platform_type)
        
        # Create unified agent
        self._unified_agent = MaestroCatAgent(config=config, platform_override=platform_type)
        
        logger.info(f"✅ Legacy agent {legacy_agent_name} wrapped with unified platform system")
    
    def _issue_deprecation_warning(self):
        """Issue deprecation warning for legacy agent usage"""
        warnings.warn(
            f"Legacy agent class '{self.legacy_agent_name}' is deprecated. "
            f"Please migrate to the unified MaestroCatAgent from core.platform. "
            f"See migration guide for details.",
            DeprecationWarning,
            stacklevel=3
        )
    
    def __getattr__(self, name):
        """Delegate all method calls to the unified agent"""
        return getattr(self._unified_agent, name)
    
    async def setup(self):
        """Legacy setup method compatibility"""
        return await self._unified_agent.setup()
    
    async def run(self):
        """Legacy run method compatibility"""
        return await self._unified_agent.run()
    
    def create_app(self):
        """Legacy create_app method compatibility"""
        return self._unified_agent.create_app()
    
    async def handle_websocket(self, websocket):
        """Legacy WebSocket handler compatibility"""
        return await self._unified_agent.handle_websocket(websocket)


def create_legacy_local_maestrocat_agent(config_file: str = "config/maestrocat.yaml"):
    """
    Factory function that creates a legacy LocalMaestroCatAgent using the new system.
    
    This function can be imported in place of the old LocalMaestroCatAgent class
    to provide seamless backward compatibility.
    """
    return LegacyAgentWrapper("LocalMaestroCatAgent", config_file)


def create_legacy_macos_maestrocat_agent(config_file: str = "config/maestrocat_macos.yaml"):
    """
    Factory function that creates a legacy MacOSMaestroCatAgent using the new system.
    
    This function can be imported in place of the old MacOSMaestroCatAgent class
    to provide seamless backward compatibility.
    """
    return LegacyAgentWrapper("MacOSMaestroCatAgent", config_file)


class ConfigMigrator:
    """
    Utilities for migrating legacy configuration files to the new unified format.
    """
    
    @staticmethod
    def migrate_legacy_config(
        docker_config_path: Union[str, Path] = "config/maestrocat.yaml",
        macos_config_path: Union[str, Path] = "config/maestrocat_macos.yaml",
        output_path: Union[str, Path] = "config/maestrocat_unified.yaml"
    ) -> bool:
        """
        Migrate legacy configuration files to unified format.
        
        Args:
            docker_config_path: Path to Docker legacy config
            macos_config_path: Path to macOS legacy config  
            output_path: Path for unified output config
            
        Returns:
            True if migration successful, False otherwise
        """
        try:
            import yaml
            
            docker_config_path = Path(docker_config_path)
            macos_config_path = Path(macos_config_path)
            output_path = Path(output_path)
            
            logger.info("🔄 Migrating legacy configurations to unified format...")
            
            # Load legacy configs
            docker_config = {}
            macos_config = {}
            
            if docker_config_path.exists():
                with open(docker_config_path, 'r') as f:
                    docker_config = yaml.safe_load(f)
                logger.info(f"📄 Loaded Docker config: {docker_config_path}")
            
            if macos_config_path.exists():
                with open(macos_config_path, 'r') as f:
                    macos_config = yaml.safe_load(f)
                logger.info(f"📄 Loaded macOS config: {macos_config_path}")
            
            if not docker_config and not macos_config:
                logger.error("❌ No legacy configuration files found")
                return False
            
            # Create unified configuration structure
            unified_config = ConfigMigrator._create_unified_structure(docker_config, macos_config)
            
            # Write unified configuration
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                yaml.dump(unified_config, f, default_flow_style=False, sort_keys=False, indent=2)
            
            logger.info(f"✅ Unified configuration written to: {output_path}")
            
            # Create backup of legacy files
            ConfigMigrator._backup_legacy_files(docker_config_path, macos_config_path)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to migrate configuration: {e}")
            return False
    
    @staticmethod
    def _create_unified_structure(docker_config: Dict, macos_config: Dict) -> Dict[str, Any]:
        """Create unified configuration structure from legacy configs"""
        # Use Docker config as base since it's more common
        base_config = docker_config or macos_config
        
        unified = {
            # Extract common sections
            "vad": base_config.get("vad", {
                "energy_threshold": 0.5,
                "min_speech_ms": 200,
                "pause_ms": 600
            }),
            
            "stt": {
                "language": base_config.get("stt", {}).get("language", "en"),
                "translate": base_config.get("stt", {}).get("translate", False)
            },
            
            "llm": {
                "model": base_config.get("llm", {}).get("model", "llama3.2:3b"),
                "temperature": base_config.get("llm", {}).get("temperature", 0.7),
                "max_tokens": base_config.get("llm", {}).get("max_tokens", 150),
                "top_p": base_config.get("llm", {}).get("top_p", 0.9),
                "top_k": base_config.get("llm", {}).get("top_k", 40),
                "system_prompt": base_config.get("llm", {}).get("system_prompt", 
                    "You are MaestroCat, a helpful AI voice assistant.")
            },
            
            "tts": {
                "voice": base_config.get("tts", {}).get("voice", "af_bella"),
                "speed": base_config.get("tts", {}).get("speed", 1.0)
            },
            
            "interruption": base_config.get("interruption", {
                "threshold": 0.2,
                "ack_delay": 0.05
            }),
            
            "modules": base_config.get("modules", {}),
            
            "development": base_config.get("development", {
                "log_level": "INFO",
                "debug_ui": True,
                "debug_port": 8080,
                "websocket_port": 8765
            }),
            
            # Platform-specific sections
            "platforms": {}
        }
        
        # Add Docker platform section
        if docker_config:
            unified["platforms"]["docker"] = {
                "stt": {
                    "service": "whisperlive",
                    "host": docker_config.get("stt", {}).get("host", "localhost"),
                    "port": docker_config.get("stt", {}).get("port", 9090),
                    "model": docker_config.get("stt", {}).get("model", "small"),
                    "sample_rate": 16000,
                    "use_vad": False
                },
                "llm": {
                    "base_url": docker_config.get("llm", {}).get("base_url", "http://localhost:11434")
                },
                "tts": {
                    "service": "kokoro",
                    "base_url": docker_config.get("tts", {}).get("base_url", "http://localhost:5000"),
                    "sample_rate": docker_config.get("tts", {}).get("sample_rate", 24000)
                },
                "vad": docker_config.get("vad", {})
            }
        
        # Add macOS platform section
        if macos_config:
            unified["platforms"]["macos_native"] = {
                "stt": {
                    "service": "mlx_whisper",
                    "model_size": macos_config.get("stt", {}).get("model_size", "base"),
                    "sample_rate": macos_config.get("stt", {}).get("sample_rate", 16000)
                },
                "llm": {
                    "base_url": macos_config.get("llm", {}).get("base_url", "http://localhost:11434")
                },
                "tts": {
                    "service": macos_config.get("tts", {}).get("service", "macos"),
                    "sample_rate": macos_config.get("tts", {}).get("sample_rate", 22050),
                    "rate": macos_config.get("tts", {}).get("rate", 180),
                    "volume": macos_config.get("tts", {}).get("volume", 0.9)
                },
                "macos": macos_config.get("macos", {}),
                "vad": macos_config.get("vad", {})
            }
        
        # Add platform selection
        unified["platform"] = {
            "auto_detect": True,
            "preferred": None,
            "fallbacks": {
                "macos_native": ["docker"],
                "docker": ["macos_native"],
                "wsl": ["docker"],
                "windows": ["docker"]
            }
        }
        
        return unified
    
    @staticmethod
    def _backup_legacy_files(*file_paths: Path):
        """Create backups of legacy configuration files"""
        for file_path in file_paths:
            if file_path.exists():
                backup_path = file_path.with_suffix(file_path.suffix + '.legacy_backup')
                try:
                    backup_path.write_text(file_path.read_text())
                    logger.info(f"📁 Created backup: {backup_path}")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to create backup for {file_path}: {e}")


class BackwardCompatibilityLayer:
    """
    Provides backward compatibility for existing imports and usage patterns.
    """
    
    @staticmethod
    def patch_legacy_imports():
        """
        Patch legacy imports to use the new unified system.
        
        This allows existing code to continue working without modification
        by redirecting imports to the new unified components.
        """
        import sys
        from types import ModuleType
        
        # Create compatibility modules
        legacy_agent_module = ModuleType('examples.local_maestrocat_agent')
        legacy_macos_module = ModuleType('examples.local_maestrocat_macos')
        
        # Add legacy classes as aliases to new system
        legacy_agent_module.LocalMaestroCatAgent = lambda config_file="config/maestrocat.yaml": create_legacy_local_maestrocat_agent(config_file)
        legacy_macos_module.MacOSMaestroCatAgent = lambda config_file="config/maestrocat_macos.yaml": create_legacy_macos_maestrocat_agent(config_file)
        
        # Register modules in sys.modules for import compatibility
        sys.modules['examples.local_maestrocat_agent'] = legacy_agent_module
        sys.modules['examples.local_maestrocat_macos'] = legacy_macos_module
        
        logger.info("✅ Legacy import compatibility layer activated")
    
    @staticmethod
    def create_migration_guide() -> str:
        """
        Generate a migration guide for users upgrading to the new system.
        
        Returns:
            Markdown-formatted migration guide
        """
        guide = """
# MaestroCat Platform Abstraction Migration Guide

## Overview

MaestroCat has been upgraded with a new unified platform abstraction system that eliminates code duplication and provides a consistent experience across all platforms.

## What Changed

### Before (Legacy)
- Separate agent classes: `LocalMaestroCatAgent`, `MacOSMaestroCatAgent`
- Platform-specific configuration files: `maestrocat.yaml`, `maestrocat_macos.yaml`
- Duplicated platform logic in launcher: `maestrocat.py`
- Manual platform-specific service initialization

### After (New System)
- Single unified agent: `MaestroCatAgent`
- Unified configuration: `maestrocat_unified.yaml` with platform sections
- Automatic platform detection and service selection
- Clean platform abstraction with strategy pattern

## Migration Steps

### 1. Update Imports

**Old:**
```python
from examples.local_maestrocat_agent import LocalMaestroCatAgent
from examples.local_maestrocat_macos import MacOSMaestroCatAgent
```

**New:**
```python
from core.platform import MaestroCatAgent
```

### 2. Update Agent Initialization

**Old:**
```python
# Docker
agent = LocalMaestroCatAgent("config/maestrocat.yaml")

# macOS
agent = MacOSMaestroCatAgent("config/maestrocat_macos.yaml")
```

**New:**
```python
# Unified (auto-detects platform)
agent = MaestroCatAgent()

# Or with specific config
agent = MaestroCatAgent(config_file="config/maestrocat_unified.yaml")

# Or force platform
from core.platform import PlatformType
agent = MaestroCatAgent(platform_override=PlatformType.MACOS_NATIVE)
```

### 3. Migrate Configuration

Run the configuration migrator:
```python
from core.platform.migration import ConfigMigrator
ConfigMigrator.migrate_legacy_config()
```

Or use the new unified launcher:
```bash
python maestrocat_unified.py --setup
```

### 4. Update Launcher Usage

**Old:**
```bash
python maestrocat.py  # Mixed platform logic
```

**New:**
```bash
python maestrocat_unified.py  # Clean unified launcher
```

## Backward Compatibility

The new system maintains full backward compatibility:

1. **Legacy Imports**: Old imports continue working with deprecation warnings
2. **Legacy Configs**: Old configuration files are supported
3. **Legacy APIs**: All existing methods and interfaces work unchanged

## Benefits

1. **No Code Duplication**: Single agent implementation for all platforms
2. **Automatic Platform Detection**: No manual platform selection needed
3. **Unified Configuration**: Single config file with platform sections
4. **Better Error Handling**: Comprehensive dependency checking and fallbacks
5. **Extensible**: Easy to add new platforms (Windows, Linux native, etc.)

## Troubleshooting

### Import Errors
If you see import errors, make sure you have the new platform module:
```python
from core.platform import MaestroCatAgent, PlatformType
```

### Configuration Issues
Use the migration utility to convert legacy configs:
```python
from core.platform.migration import ConfigMigrator
ConfigMigrator.migrate_legacy_config()
```

### Platform Detection Issues
Check platform compatibility:
```bash
python maestrocat_unified.py --check
```

## Getting Help

- Check platform status: `python maestrocat_unified.py --status`
- Run compatibility check: `python maestrocat_unified.py --check`
- View migration guide: Import `core.platform.migration` and call `create_migration_guide()`
"""
        return guide


def install_backward_compatibility():
    """
    Install backward compatibility layer for seamless migration.
    
    This function should be called at the start of the application to ensure
    that legacy code continues to work without modification.
    """
    try:
        BackwardCompatibilityLayer.patch_legacy_imports()
        logger.info("✅ Backward compatibility layer installed")
    except Exception as e:
        logger.warning(f"⚠️  Failed to install backward compatibility layer: {e}")


# Auto-install compatibility layer when module is imported
install_backward_compatibility()