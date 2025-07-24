# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## MaestroCat Overview

MaestroCat is a Pipecat extension for building local voice agents with ultra-low latency (<500ms), smart interruption handling, and a modular architecture. It extends Pipecat without forking, providing custom services and processors for 100% local voice AI.

## Common Development Commands

### Setup and Dependencies

#### Docker-based Setup (Linux/Windows)
```bash
# Install Pipecat with required extras
pip install "pipecat-ai[silero,websockets,openai,ollama]>=0.0.76"

# Install MaestroCat in development mode with all dependencies
pip install -e ".[dev]"

# Install specific feature sets
pip install -e ".[whisperlive]"  # For WhisperLive STT support (includes pyaudio)
pip install -e ".[debug]"         # For debug UI and metrics
pip install -e ".[all]"           # All optional features
```

#### Native macOS Setup (Apple Silicon)
```bash
# Install native dependencies via Homebrew
brew install ollama whisper-cpp ffmpeg

# Install Pipecat with required extras
pip install "pipecat-ai[silero,websockets,openai,ollama]>=0.0.76"

# Install MaestroCat with development dependencies
pip install -e ".[dev]"

# Optional: Install PyTTSx3 for alternative TTS
pip install pyttsx3 pyobjc

# Start Ollama server and download model
ollama serve &
ollama pull llama3.2:3b
```

### Running Services

MaestroCat automatically detects your platform and starts the appropriate services when you run `python maestrocat.py`.

#### Automatic Platform Detection
```bash
# Universal launcher - detects platform and starts appropriate services
python maestrocat.py

# Check dependencies only  
python maestrocat.py --check-only

# Force specific platform
python maestrocat.py --platform macos
python maestrocat.py --platform linux
```

#### Manual Service Management

**Linux/WSL (GPU-enabled)**:
```bash
# Start GPU-accelerated services
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# Start just Kokoro TTS with GPU
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up kokoro -d
```

**macOS or CPU-only systems**:
```bash
# Start CPU-only services (Kokoro TTS) 
docker-compose -f docker-compose.yml -f docker-compose.cpu.yml up -d

# Start just Kokoro TTS (CPU)
docker-compose -f docker-compose.yml -f docker-compose.cpu.yml up kokoro -d

# Native Ollama (macOS) - Recommended
ollama serve
```

#### Manual Docker Image Management

**Pull Kokoro images manually (optional)**:
```bash
# For macOS or CPU-only systems
docker pull ghcr.io/remsky/kokoro-fastapi-cpu:latest

# For Linux/WSL with GPU
docker pull ghcr.io/remsky/kokoro-fastapi-gpu:latest

# Check downloaded images
docker images | grep kokoro
```

#### Service Health Checks
```bash
# Check all services
docker-compose ps

# View service logs
docker-compose logs kokoro

# Check Kokoro TTS web UI
open http://localhost:5000/web

# Test Ollama API
curl http://localhost:11434/api/version
```

### Running the Application

#### Docker-based Agent
```bash
# Run main voice agent (uses config/maestrocat.yaml)
python run.py

# Run example agents
python examples/local_maestrocat_agent.py
```

#### Native macOS Agent
```bash
# Run macOS native agent (uses config/maestrocat_macos.yaml)
python examples/local_maestrocat_macos.py

# Test with specific configuration
python examples/local_maestrocat_macos.py --config config/maestrocat_macos.yaml
```

### Testing
```bash
# Run integration tests
python integration_tests/run_tests.py all
python integration_tests/run_tests.py latency  # Just latency tests
python integration_tests/run_tests.py stress   # Just stress tests

# Run unit tests (when available)
pytest
```

### Code Quality
```bash
# Format code
black maestrocat/ core/

# Lint code  
ruff check maestrocat/ core/

# Type checking (if configured)
mypy maestrocat/ core/
```

## Architecture

### Core Components Structure

MaestroCat extends Pipecat through four main component types:

1. **Services** (`core/services/`): Interface with external systems
   - `WhisperLiveSTTService`: WebSocket-based real-time speech-to-text (Docker)
   - `WhisperCppSTTService`: Native Whisper.cpp STT for macOS
   - `OLLamaLLMService`: Local LLM inference with streaming
   - `KokoroTTSService`: High-quality local text-to-speech (Docker)
   - `MacOSTTSService`: Native macOS system TTS
   - `MacOSPyTTSx3Service`: Alternative TTS using PyTTSx3

2. **Processors** (`core/processors/`): Pipeline data transformation
   - `InterruptionHandler`: Smart interruption with context preservation (threshold-based)
   - `MetricsCollector`: Real-time performance monitoring
   - `EventEmitter`: Enhanced pub/sub event system
   - `ModuleLoader`: Dynamic module loading system

3. **Transports** (`core/transports/`): Audio I/O handling
   - `WSLAudioTransport`: Windows Subsystem for Linux audio support
   - `CustomPyAudioTransport`: Enhanced PyAudio with better buffering
   - `FastAPIWebsocketTransport`: WebSocket-based audio streaming

4. **Modules** (`core/modules/`): Extensible functionality
   - Base class `MaestroCatModule` for creating custom modules
   - Example modules: `VoiceRecognitionModule`, `MemoryModule`

### Pipeline Architecture

The pipeline follows Pipecat's design:
```
Audio Input → STT → User Context → LLM → Assistant Context → TTS → Audio Output
                ↓                    ↓                         ↓
           Processors           Processors               Processors
                ↓                    ↓                         ↓
             Events               Events                   Events
```

### Configuration System

MaestroCat uses YAML configuration with platform-specific options:

#### Docker Configuration (`config/maestrocat.yaml`)
- VAD (Voice Activity Detection) parameters
- STT (WhisperLive) Docker service settings
- LLM (Ollama) Docker service configuration
- TTS (Kokoro) Docker service settings
- Interruption handling thresholds
- Module enablement

#### macOS Native Configuration (`config/maestrocat_macos.yaml`)
- STT (Whisper.cpp) native settings with model selection
- LLM (Ollama) native service configuration
- TTS (macOS System/PyTTSx3) native voice settings
- Apple Silicon performance optimizations
- Metal GPU acceleration settings

### Event System

The `EventEmitter` processor broadcasts events that modules can subscribe to:
- `transcription_complete`: When STT finishes
- `llm_response_start/complete`: LLM generation events
- `tts_audio_start/complete`: TTS synthesis events
- `interruption_detected`: When user interrupts

## Key Implementation Details

### Interruption Handling
The `InterruptionHandler` uses a threshold system (default 0.2 = 20%) to determine whether to preserve context when interrupted. If less than 20% of the response was delivered, it preserves the full context for continuation.

### Service Communication

#### Docker Services
- WhisperLive: WebSocket connection on port 9090
- Kokoro: HTTP API on port 5000 (mapped from 8880 in container)

#### Native macOS Services
- Whisper.cpp: Subprocess execution with temporary WAV files
- Ollama: HTTP API on port 11434 (native binary)
- macOS TTS: System `say` command or PyTTSx3 library

### Audio Processing

#### Docker Setup
- Sample rates: 24kHz for Kokoro TTS (high quality), 16kHz for WhisperLive
- Audio formats: PCM 16-bit for all services
- Buffering: Custom buffering in transports for smooth playback

#### macOS Native Setup
- Sample rates: 22kHz for macOS TTS, 16kHz for Whisper.cpp
- Audio formats: PCM 16-bit with automatic conversion
- Apple Silicon optimizations: Metal acceleration, Core ML where available

### Module System
Modules inherit from `MaestroCatModule` and implement:
- `async def on_event(event_type: str, data: Any)`: Event handler
- `async def initialize()`: Setup code
- Modules are loaded dynamically by `ModuleLoader` processor

## Docker Services

- **whisperlive**: GPU-accelerated real-time STT (faster_whisper backend)
- **kokoro**: GPU-accelerated TTS with multiple voices
- **redis**: Optional distributed event bus (port 6379)

All services use the `maestrocat-network` Docker network for inter-service communication.

## Performance Considerations

### Docker Setup
- Use smaller models for lower latency (e.g., whisper tiny/small, llama 1B/3B)
- GPU acceleration significantly improves all services
- The pipeline is designed for <500ms total latency
- Interruption handling adds minimal overhead (~50ms acknowledgment)

### macOS Native Setup
- Apple Silicon optimization: Use Metal acceleration where available
- Recommended models: Whisper base/small, Llama 3.2 1B/3B for M1/M2, up to 7B for M3 Pro/Max
- Native performance often exceeds Docker equivalents
- Memory usage typically lower due to native compilation
- Consider Core ML acceleration for Whisper.cpp when available

### Platform Comparison
- **Docker**: Better for development consistency, easier service management
- **macOS Native**: Better performance, lower resource usage, no Docker overhead
- **Hybrid**: Use native Ollama with Docker STT/TTS for flexibility