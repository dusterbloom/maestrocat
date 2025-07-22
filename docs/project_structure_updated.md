# MaestroCat Project Structure

```
maestrocat/
├── README.md
├── setup.py
├── requirements.txt
├── .env.example
├── docker-compose.yml
│
├── maestrocat/
│   ├── __init__.py
│   ├── version.py
│   │
│   ├── processors/           # Custom Pipecat processors
│   │   ├── __init__.py
│   │   ├── interruption.py   # Smart interruption handling
│   │   ├── metrics.py        # Performance metrics collector
│   │   ├── event_emitter.py  # Enhanced event system
│   │   └── module_loader.py  # Module system processor
│   │
│   ├── services/            # Custom Pipecat services
│   │   ├── __init__.py
│   │   ├── whisperlive_stt.py
│   │   ├── ollama_llm.py
│   │   ├── kokoro_tts.py
│   │   └── piper_tts.py
│   │
│   ├── modules/             # MaestroCat modules (voice rec, memory, etc)
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── voice_recognition.py
│   │   ├── memory.py
│   │   └── personality.py
│   │
│   ├── transports/          # Custom transports if needed
│   │   ├── __init__.py
│   │   └── debug_transport.py
│   │
│   ├── utils/              # Utilities
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── state.py
│   │   └── events.py
│   │
│   └── apps/               # Complete applications
│       ├── __init__.py
│       ├── debug_ui.py     # FastAPI debug UI server
│       └── voice_agent.py  # Main voice agent app
│
├── examples/               # Example implementations
│   ├── basic_agent.py
│   ├── interruption_demo.py
│   ├── multi_language.py
│   └── with_memory.py
│
├── tests/                  # Tests
│   ├── test_services.py
│   ├── test_processors.py
│   └── test_integration.py
│
├── ui/                     # Debug UI (React app)
│   ├── package.json
│   ├── src/
│   └── public/
│
└── config/                 # Configuration files
    ├── maestrocat.yaml
    └── presets/
        ├── low_latency.yaml
        ├── high_quality.yaml
        └── multilingual.yaml
```

## Key Design Principles

1. **Pure Extension**: MaestroCat only extends Pipecat, never modifies it
2. **Standard Interfaces**: All components follow Pipecat's interfaces
3. **Pip Installable**: Can be installed alongside Pipecat
4. **Zero Fork**: Uses Pipecat as a dependency, not a base

## Installation

```bash
# Install Pipecat with desired extras
pip install "pipecat-ai[silero,websockets]"

# Install MaestroCat
pip install maestrocat

# Or for development
pip install -e .
```

## How It Works

MaestroCat provides:

1. **Custom Services** that implement Pipecat's service interfaces
2. **Custom Processors** that extend FrameProcessor
3. **Helper utilities** for common patterns
4. **Pre-built applications** using these components

Everything is built using Pipecat's public APIs and extension points.