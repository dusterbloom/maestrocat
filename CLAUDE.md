# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## MaestroCat Overview

MaestroCat is a Pipecat extension for building local voice agents with ultra-low latency (<500ms), smart interruption handling, and a modular architecture. It extends Pipecat without forking, providing custom services and processors for 100% local voice AI.

## Common Development Commands

### Setup and Dependencies
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

### Running Services
```bash
# Start all Docker services (WhisperLive, Ollama, Kokoro TTS)
docker-compose up -d

# Check service health
docker-compose ps

# View service logs
docker-compose logs <service_name>  # e.g., whisperlive, ollama, kokoro
```

### Running the Application
```bash
# Run main voice agent (uses config/maestrocat.yaml)
python run.py

# Run example agents
python examples/local_maestrocat_agent.py
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
   - `WhisperLiveSTTService`: WebSocket-based real-time speech-to-text
   - `OLLamaLLMService`: Local LLM inference with streaming
   - `KokoroTTSService`: High-quality local text-to-speech

2. **Processors** (`core/processors/`): Pipeline data transformation
   - `InterruptionHandler`: Smart interruption with context preservation (threshold-based)
   - `MetricsCollector`: Real-time performance monitoring
   - `EventEmitter`: Enhanced pub/sub event system
   - `ModuleLoader`: Dynamic module loading system

3. **Transports** (`core/transports/`): Audio I/O handling
   - `WSLAudioTransport`: Windows Subsystem for Linux audio support
   - `CustomPyAudioTransport`: Enhanced PyAudio with better buffering

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

MaestroCat uses YAML configuration (`config/maestrocat.yaml`) with sections for:
- VAD (Voice Activity Detection) parameters
- STT (WhisperLive) settings
- LLM (Ollama) configuration including system prompts
- TTS (Kokoro) voice settings
- Interruption handling thresholds
- Module enablement

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
- WhisperLive: WebSocket connection on port 9090
- Ollama: HTTP API on port 11434  
- Kokoro: HTTP API on port 5000 (mapped from 8880 in container)

### Audio Processing
- Sample rates: 24kHz for Kokoro TTS (high quality)
- Audio formats: PCM 16-bit for all services
- Buffering: Custom buffering in transports for smooth playback

### Module System
Modules inherit from `MaestroCatModule` and implement:
- `async def on_event(event_type: str, data: Any)`: Event handler
- `async def initialize()`: Setup code
- Modules are loaded dynamically by `ModuleLoader` processor

## Docker Services

- **whisperlive**: GPU-accelerated real-time STT (faster_whisper backend)
- **kokoro**: GPU-accelerated TTS with multiple voices
- **ollama**: Local LLM inference (manages model downloads)
- **redis**: Optional distributed event bus (port 6379)

All services use the `maestrocat-network` Docker network for inter-service communication.

## Performance Considerations

- Use smaller models for lower latency (e.g., whisper tiny/small, llama 1B/3B)
- GPU acceleration significantly improves all services
- The pipeline is designed for <500ms total latency
- Interruption handling adds minimal overhead (~50ms acknowledgment)