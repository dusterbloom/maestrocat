# MaestroCat 🎭🐱

A Pipecat extension for building local voice agents with enhanced debugging, smart interruption handling, and modular architecture.

## Features

- 🚀 **Ultra-low latency** voice interactions (< 500ms)
- 🎯 **Smart interruption handling** with context preservation
- 🔍 **Real-time debug UI** for monitoring and configuration
- 🧩 **Modular architecture** for voice recognition and memory
- 🏠 **100% local** - no cloud dependencies
- 🔧 **Hot-swappable** components and configuration

## Architecture

MaestroCat extends [Pipecat](https://github.com/pipecat-ai/pipecat) without forking, providing:

- **Custom Services**: WhisperLive STT, Ollama LLM, Kokoro/Piper TTS
- **Custom Processors**: Interruption handling, metrics collection, event system
- **Module System**: Extensible modules for voice recognition, memory, etc.
- **Debug UI**: Real-time monitoring and configuration

## Quick Start

### Prerequisites

- Python 3.10+
- Docker and Docker Compose
- Microphone access (for local testing)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/maestrocat.git
cd maestrocat

# Install Pipecat and MaestroCat
pip install "pipecat-ai[silero,daily]"
pip install -e .

# Start the services
docker-compose up -d

# Verify services are running
docker-compose ps
```

### Basic Usage

```python
from pipecat.pipeline.pipeline import Pipeline
from pipecat.transports.services.daily import DailyTransport
from maestrocat.processors import InterruptionHandler, MetricsCollector
from maestrocat.services import WhisperLiveSTTService, OllamaLLMService, KokoroTTSService

# Create services
stt = WhisperLiveSTTService(host="localhost", port=9090)
llm = OllamaLLMService(model="llama3.2:3b", temperature=0.7)
tts = KokoroTTSService(voice="af_bella")

# Create processors
interruption = InterruptionHandler(threshold=0.2)
metrics = MetricsCollector()

# Build pipeline
pipeline = Pipeline([
    transport.input(),
    stt,
    interruption,
    llm,
    tts,
    metrics,
    transport.output()
])
```

### Run Example Agent

```bash
# With Daily transport
python examples/maestrocat_voice_agent.py

# With WebSocket transport
python examples/maestrocat_voice_agent.py --websocket

# Access debug UI
open http://localhost:8080
```

## Components

### Services

- **WhisperLiveSTTService**: Real-time speech-to-text using Collabora's WhisperLive
- **OllamaLLMService**: Local LLM inference with streaming support
- **KokoroTTSService**: High-quality text-to-speech (or Piper as alternative)

### Processors

- **InterruptionHandler**: Smart interruption with context preservation
- **MetricsCollector**: Performance monitoring and reporting
- **EventEmitter**: Enhanced pub/sub event system
- **ModuleLoader**: Dynamic module loading system

### Modules

- **VoiceRecognitionModule**: Speaker identification (example)
- **MemoryModule**: Conversation history and context

## Configuration

Create `config/maestrocat.yaml`:

```yaml
vad:
  energy_threshold: 0.5
  min_speech_ms: 250
  pause_ms: 800

stt:
  host: "localhost"
  port: 9090
  language: "en"
  model: "small"

llm:
  base_url: "http://localhost:11434"
  model: "llama3.2:3b"
  temperature: 0.7
  system_prompt: |
    You are a helpful AI assistant.
    Keep responses concise and conversational.

tts:
  base_url: "http://localhost:5000"
  voice: "af_bella"
  speed: 1.0

interruption:
  threshold: 0.2  # Preserve context if <20% complete
  ack_delay: 0.05  # 50ms acknowledgment pause
```

## Debug UI

Access the debug UI at http://localhost:8080 to:

- Monitor real-time pipeline latency
- Adjust LLM temperature, TTS speed, etc.
- View conversation history
- Track loaded modules
- Inspect event stream

## Creating Custom Modules

```python
from maestrocat.modules.base import MaestroCatModule

class MyModule(MaestroCatModule):
    async def on_event(self, event_type: str, data: Any):
        if event_type == "transcription_complete":
            # Process transcription
            text = data.get("text", "")
            # Your logic here
            
    async def initialize(self):
        # Setup code
        pass
```

## Docker Services

- **WhisperLive**: WebSocket-based real-time STT
- **Ollama**: Local LLM inference
- **Piper**: Local TTS (Kokoro alternative)
- **Redis**: Optional distributed event bus
- **Prometheus**: Optional metrics collection

## Performance

- STT latency: ~150ms (WhisperLive)
- LLM first token: ~200ms (Llama 3.2 3B)
- TTS first audio: ~100ms (Piper)
- Total latency: < 500ms typical

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black maestrocat/
ruff check maestrocat/

# Build Docker images locally
docker-compose build
```

## Troubleshooting

### No audio detected
- Check microphone permissions
- Verify audio device: `python -m sounddevice`

### High latency
- Use smaller models (tiny STT, 1B LLM)
- Enable GPU acceleration if available
- Check CPU/memory usage

### Connection errors
- Verify all services are running: `docker-compose ps`
- Check service logs: `docker-compose logs <service>`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - See LICENSE file

## Acknowledgments

- Built on top of [Pipecat](https://github.com/pipecat-ai/pipecat)
- Uses [WhisperLive](https://github.com/collabora/WhisperLive) for STT
- Powered by [Ollama](https://ollama.ai) for local LLMs

## Links

- [Documentation](https://github.com/yourusername/maestrocat/wiki)
- [Examples](https://github.com/yourusername/maestrocat/tree/main/examples)
- [Discord Community](#)
- [Blog Post](#)