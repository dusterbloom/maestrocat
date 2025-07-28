# MaestroCat Platform Abstraction System

## Overview

MaestroCat now features a comprehensive platform abstraction system that eliminates code duplication, provides consistent functionality across platforms, and enables easy addition of new platform support.

## Key Components

### 1. Platform Strategy Pattern

The system uses the Strategy pattern to encapsulate platform-specific logic:

```python
from core.platform import MaestroCatAgent, PlatformType

# Automatic platform detection and optimization
agent = MaestroCatAgent()

# Force specific platform
agent = MaestroCatAgent(platform_override=PlatformType.MACOS_NATIVE)
```

### 2. Unified Configuration

Single configuration file with platform-specific sections:

```yaml
# Base configuration (applies to all platforms)
vad:
  energy_threshold: 0.5
  min_speech_ms: 200

llm:
  model: "llama3.2:3b"
  temperature: 0.7

# Platform-specific overrides
platforms:
  docker:
    stt:
      service: "whisperlive"
      host: "localhost"
      port: 9090
    
  macos_native:
    stt:
      service: "mlx_whisper"
      model_size: "base"
```

### 3. Automatic Platform Detection

Intelligent platform detection with capability assessment:

```python
from core.platform import PlatformDetector

# Get comprehensive platform info
platform_info = PlatformDetector.detect_full_platform_info()
print(f"Platform: {platform_info.description}")
print(f"MLX Support: {platform_info.capabilities.supports_mlx}")
print(f"GPU Available: {platform_info.capabilities.has_gpu}")
```

## Supported Platforms

### Docker Platform (Linux, Windows, WSL)
- **Services**: WhisperLive STT, Ollama LLM, Kokoro TTS
- **Features**: GPU/CPU variants, automatic service management
- **Optimizations**: GPU acceleration when available

### macOS Native Platform
- **Services**: MLX Whisper STT, Native Ollama, macOS/PyTTSx3/Native Kokoro TTS
- **Features**: Apple Silicon optimizations, Metal acceleration
- **Optimizations**: MLX framework integration, lower latency

## Architecture

```
MaestroCatAgent
├── PlatformStrategy (Abstract)
│   ├── DockerPlatformStrategy
│   ├── MacOSPlatformStrategy
│   └── [Future: LinuxNativeStrategy, WindowsStrategy]
├── PlatformDetector
├── ServiceFactory
└── UnifiedConfiguration
```

## Usage Examples

### Basic Usage

```python
from core.platform import MaestroCatAgent

# Simple auto-detection
agent = MaestroCatAgent()
await agent.run()
```

### Advanced Configuration

```python
from core.platform import MaestroCatAgent, PlatformType
from core.platform.config import UnifiedMaestroCatConfig

# Load custom unified config
config = UnifiedMaestroCatConfig.from_file("config/custom.yaml")
agent = MaestroCatAgent(config=config)

# Force specific platform with custom config
agent = MaestroCatAgent(
    config_file="config/custom.yaml",
    platform_override=PlatformType.MACOS_NATIVE
)
```

### Platform Information

```python
from core.platform import PlatformDetector, ServiceFactory

# Get platform recommendations
recommendations = ServiceFactory.get_strategy_recommendations({})
print(f"Recommended: {recommendations['recommended_strategy']}")

# Check platform compatibility
platform_info = PlatformDetector.detect_full_platform_info()
print(f"Native services: {platform_info.capabilities.native_services}")
```

## Command Line Interface

### New Unified Launcher

```bash
# Auto-detect and run
python maestrocat_unified.py

# Check platform compatibility
python maestrocat_unified.py --check

# Show platform status
python maestrocat_unified.py --status

# Use custom config
python maestrocat_unified.py --config config/custom.yaml

# Force platform
python maestrocat_unified.py --platform macos_native
```

### Legacy Compatibility

```bash
# Legacy launcher (deprecated but still works)
python maestrocat.py  # Redirects to unified launcher with warning
```

## Migration Guide

### From Legacy Agents

**Old:**
```python
from examples.local_maestrocat_agent import LocalMaestroCatAgent
from examples.local_maestrocat_macos import MacOSMaestroCatAgent

# Platform-specific agents
docker_agent = LocalMaestroCatAgent("config/maestrocat.yaml")
macos_agent = MacOSMaestroCatAgent("config/maestrocat_macos.yaml")
```

**New:**
```python
from core.platform import MaestroCatAgent

# Unified agent (auto-detects platform)
agent = MaestroCatAgent()

# Or with legacy config files (backward compatible)
agent = MaestroCatAgent(config_file="config/maestrocat.yaml")
```

### Configuration Migration

Use the built-in migrator:

```python
from core.platform.migration import ConfigMigrator

# Migrate legacy configs to unified format
ConfigMigrator.migrate_legacy_config(
    docker_config_path="config/maestrocat.yaml",
    macos_config_path="config/maestrocat_macos.yaml", 
    output_path="config/maestrocat_unified.yaml"
)
```

## Adding New Platforms

### 1. Create Platform Strategy

```python
from core.platform.strategy import PlatformStrategy, PlatformType, PlatformInfo

class WindowsPlatformStrategy(PlatformStrategy):
    @property
    def platform_info(self) -> PlatformInfo:
        return PlatformInfo(
            platform_type=PlatformType.WINDOWS,
            capabilities=self._detect_capabilities(),
            description="Windows with Docker services"
        )
    
    async def create_stt_service(self, event_emitter=None):
        # Windows-specific STT implementation
        pass
    
    # ... implement other abstract methods
```

### 2. Register Strategy

```python
from core.platform import ServiceFactory, PlatformType

ServiceFactory.register_strategy(PlatformType.WINDOWS, WindowsPlatformStrategy)
```

### 3. Add Platform Detection

```python
from core.platform.detector import PlatformDetector

# Extend platform detection logic
def detect_windows_capabilities():
    # Windows-specific capability detection
    pass
```

## Performance Optimizations

### Apple Silicon (macOS)
- **MLX Whisper**: Hardware-accelerated speech recognition
- **Metal GPU**: Graphics acceleration for supported models
- **Native Services**: Lower overhead than Docker containers

### GPU Acceleration (Linux/Docker)
- **CUDA Support**: Automatic GPU detection and utilization
- **GPU Models**: Optimized model selection based on available VRAM
- **Parallel Processing**: GPU-accelerated STT, LLM, and TTS

### Automatic Model Selection
- **Platform-aware**: Selects optimal models based on hardware capabilities
- **Performance-first**: Prioritizes low latency for real-time voice interaction
- **Fallback Support**: Graceful degradation when optimal services unavailable

## Debugging and Monitoring

### Platform Status
```bash
python maestrocat_unified.py --status
```

### Health Monitoring
```python
agent = MaestroCatAgent()
await agent.setup()

# Get detailed health info
health = agent.strategy.get_health_info()
print(f"Platform: {health['platform_type']}")
print(f"Services: {health['service_urls']}")
```

### Debug UI Integration
The unified agent automatically configures the debug UI with platform-specific information, accessible at `http://localhost:8080`.

## Backward Compatibility

The platform abstraction system maintains 100% backward compatibility:

1. **Legacy Imports**: Old agent classes work with deprecation warnings
2. **Legacy Configs**: Existing YAML files are fully supported
3. **Legacy APIs**: All existing methods and interfaces unchanged
4. **Migration Tools**: Automated migration utilities provided

## Benefits

1. **No Code Duplication**: Single implementation for all platforms
2. **Consistent Interface**: Same APIs work across all platforms  
3. **Automatic Optimization**: Platform-specific optimizations applied automatically
4. **Easy Extension**: New platforms can be added without touching existing code
5. **Better Testing**: Unified test suite covers all platforms
6. **Simplified Deployment**: Single binary works everywhere

## Best Practices

1. **Use Unified Config**: Prefer `maestrocat_unified.yaml` for new deployments
2. **Let Auto-Detection Work**: Don't force platform types unless necessary
3. **Check Compatibility**: Use `--check` flag before deployment
4. **Monitor Health**: Use health endpoints for production monitoring
5. **Plan Migration**: Use migration tools for existing deployments

## Troubleshooting

### Platform Detection Issues
```bash
# Check what platform is detected
python maestrocat_unified.py --status

# Force specific platform if detection fails
python maestrocat_unified.py --platform docker
```

### Service Startup Problems
```bash
# Check dependencies
python maestrocat_unified.py --check

# Set up services only
python maestrocat_unified.py --setup
```

### Configuration Issues
```python
# Migrate legacy configs
from core.platform.migration import ConfigMigrator
ConfigMigrator.migrate_legacy_config()

# Validate unified config
config = UnifiedMaestroCatConfig.from_file("config/maestrocat_unified.yaml")
print(config.to_dict())
```

## Future Roadmap

1. **Windows Native Strategy**: Native Windows services without Docker
2. **Linux Native Strategy**: Native Linux services (PulseAudio, etc.)
3. **Cloud Platform Strategy**: Cloud-based services (AWS, GCP, Azure)
4. **Embedded Strategy**: Raspberry Pi and embedded device support
5. **Container Orchestration**: Kubernetes and Docker Swarm support