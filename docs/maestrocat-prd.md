# MaestroCat Product Requirements Document

*A Pipecat-based local voice agent development platform for building trust-based, relationship-aware AI agents*

## Executive Summary

### Vision
MaestroCat extends Pipecat to create a developer-first platform for building local, ultra-low latency voice agents with advanced debugging capabilities and a modular architecture designed for relationship-building features.

### Core Value Propositions
1. **Built on Pipecat** - Leverage proven real-time voice orchestration
2. **Local-first** - Privacy-preserving with no cloud dependencies
3. **Developer-focused** - Comprehensive debug UI with real-time configuration
4. **Relationship-ready** - Modular architecture for voice recognition and memory
5. **Ultra-low latency** - Sub-500ms response times with smart interruption handling

### Success Metrics
- Setup time: < 10 minutes from clone to first conversation
- Developer productivity: Add new module in < 2 hours
- Performance: < 500ms e2e latency, < 100ms interruption response
- Stability: Zero crashes in 24-hour continuous operation

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    MaestroCat Debug UI                       │
│  (React + Material-UI + WebSocket + Real-time Visualization) │
├─────────────────────────────────────────────────────────────┤
│                  MaestroCat Event Layer                      │
│        (Enhanced Pipecat Events + Module Events)             │
├─────────────────────────────────────────────────────────────┤
│                  MaestroCat Core                             │
│         (Configuration Manager + State Store)                │
├─────────────────────────────────────────────────────────────┤
│                    Pipecat Framework                         │
│          (Pipeline + Transport + Processors)                 │
├──────────────┬────────────────┬────────────────┬───────────┤
│   VAD/STT    │      LLM       │      TTS       │  Modules  │
│   (Local)    │   (Ollama)     │    (Piper)     │  (Future) │
└──────────────┴────────────────┴────────────────┴───────────┘
```

## Functional Requirements

### 1. MaestroCat Core Extensions

#### 1.1 Enhanced Event System
Building on Pipecat's event system:
- **Event Categories:**
  - Pipeline events (from Pipecat)
  - Module events (voice_identified, memory_updated)
  - Performance events (latency measurements)
  - Debug events (configuration changes)
- **Event Replay:** Last 1000 events buffered for debugging
- **Event Filtering:** Real-time filtering in debug UI

#### 1.2 Configuration Management
- **Preset System:**
  ```python
  presets = {
      "low_latency": {
          "vad": {"energy_threshold": 0.5, "pause_duration": 0.8},
          "stt": {"model": "whisper-base", "language": "auto"},
          "llm": {"model": "llama3.2:3b", "temperature": 0.7},
          "tts": {"voice": "en_US-lessac-medium", "speed": 1.2}
      },
      "high_quality": {...}
  }
  ```
- **Hot-swapping:** Change models without restart
- **Validation:** Ensure compatible model combinations

#### 1.3 State Management
```python
class MaestroCatState:
    session_id: str
    conversation_history: List[Turn]
    current_speaker: Optional[str]  # For voice recognition
    user_profile: Dict[str, Any]    # For memory system
    performance_metrics: Dict[str, float]
    module_states: Dict[str, Any]
```

### 2. Interruption System

#### 2.1 Smart Interruption Handler
```python
class InterruptionHandler:
    def __init__(self):
        self.interruption_threshold = 0.2  # 20% completion
        self.acknowledgment_delay = 50  # ms
        
    async def handle_interruption(self, context):
        # Immediate TTS stop
        await self.stop_tts()
        
        # Check if we should preserve context
        if context.completion_ratio < self.interruption_threshold:
            context.preserve_partial_response()
        
        # Add interruption marker
        context.add_system_message("[USER_INTERRUPTED]")
        
        # Brief acknowledgment pause
        await asyncio.sleep(self.acknowledgment_delay / 1000)
```

### 3. Debug UI Specifications

#### 3.1 Layout Components

**Pipeline Visualizer (Top Panel)**
```
[Mic] → [VAD: Active] → [STT: Whisper] → [LLM: Llama3.2] → [TTS: Piper] → [Speaker]
         ↓ 12ms          ↓ 145ms          ↓ 238ms          ↓ 89ms
```

**Configuration Panel (Right Sidebar)**
- Preset dropdown with instant apply
- Component-specific settings:
  - STT: Model size, language, beam size
  - LLM: Model, temperature, max tokens, context window
  - TTS: Voice, speed (0.5-2.0x), pitch
  - VAD: Energy threshold slider
- "Save as Preset" button

**Conversation View (Center)**
- Real-time transcription display
- Partial transcriptions in gray
- Interruption markers
- Latency badges on each message

**Event Log (Bottom)**
- Filterable by event type
- Expandable event details
- Performance warnings highlighted

**Module Status (Left Sidebar)**
- Loaded modules with health indicators
- Quick enable/disable toggles
- Module-specific mini-dashboards

#### 3.2 WebSocket Protocol
```typescript
// Configuration updates
{
  type: 'config_update',
  component: 'llm',
  settings: {
    model: 'llama3.2:7b',
    temperature: 0.8
  }
}

// Real-time events
{
  type: 'pipeline_event',
  timestamp: 1234567890,
  event: 'transcription_final',
  data: {
    text: "Hello, how are you?",
    confidence: 0.95,
    latency_ms: 145
  }
}
```

### 4. Module System

#### 4.1 Module Interface
```python
from maestrocat.modules import BaseModule

class VoiceRecognitionModule(BaseModule):
    def __init__(self, config):
        super().__init__("voice_recognition", config)
        
    async def process_audio(self, audio_chunk):
        # Process audio for voice identification
        pass
        
    async def on_pipeline_event(self, event):
        if event.type == "speech_started":
            speaker_id = await self.identify_speaker(event.audio)
            await self.emit_event("speaker_identified", {
                "speaker_id": speaker_id,
                "confidence": 0.92
            })
            
    def enrich_context(self, context):
        context["current_speaker"] = self.current_speaker
        return context
```

#### 4.2 Module Manager
```python
class ModuleManager:
    def __init__(self):
        self.modules = {}
        self.event_bus = EventBus()
        
    async def load_module(self, module_class, config):
        module = module_class(config)
        self.modules[module.name] = module
        await module.initialize()
        
    async def broadcast_event(self, event):
        for module in self.modules.values():
            await module.on_pipeline_event(event)
```

### 5. Local Model Integration

#### 5.1 Model Configuration
```yaml
models:
  stt:
    whisper:
      models_dir: "./models/whisper"
      available: ["base", "small", "medium"]
      default: "base"
  llm:
    ollama:
      base_url: "http://localhost:11434"
      models: ["llama3.2:3b", "llama3.2:7b", "mistral:7b"]
      default: "llama3.2:3b"
  tts:
    piper:
      models_dir: "./models/piper"
      voices: ["en_US-lessac-medium", "en_US-amy-medium"]
      default: "en_US-lessac-medium"
```

#### 5.2 Model Manager
- Automatic model downloading
- Model health checks
- Fallback handling
- Resource monitoring

## Non-Functional Requirements

### Performance
- Cold start: < 30 seconds (including model loading)
- Hot reload: < 5 seconds for configuration changes
- Memory usage: < 4GB for base configuration
- CPU usage: < 50% on 4-core system during conversation

### Developer Experience
- Single command setup: `docker-compose up`
- Comprehensive logging with context
- Example modules provided
- API documentation with examples

### Reliability
- Graceful degradation on component failure
- Automatic recovery from crashes
- State persistence across restarts
- Health monitoring endpoints

## Implementation Roadmap

### Phase 1: Core MaestroCat (Week 1-2)
1. Fork and extend Pipecat
2. Implement enhanced event system
3. Build configuration management
4. Create interruption handler
5. Add state management

### Phase 2: Debug UI (Week 2-3)
1. React app with Material-UI
2. WebSocket server
3. Pipeline visualizer
4. Configuration controls
5. Event log implementation

### Phase 3: Local Model Integration (Week 3-4)
1. Whisper integration via Pipecat
2. Ollama adapter
3. Piper TTS setup
4. Model management system
5. Docker compose configuration

### Phase 4: Module System (Week 4-5)
1. Module interface definition
2. Module manager implementation
3. Example voice recognition stub
4. Example memory system stub
5. Module documentation

### Phase 5: Polish & Documentation (Week 5-6)
1. Performance optimization
2. Comprehensive testing
3. Developer documentation
4. Example applications
5. Community setup

## Example Usage

```python
# main.py
from maestrocat import MaestroCat, InterruptionHandler
from maestrocat.modules import VoiceRecognitionModule

async def main():
    # Initialize MaestroCat with custom config
    maestro = MaestroCat(
        config_file="config.yaml",
        debug_ui=True,
        debug_port=8080
    )
    
    # Load modules
    await maestro.load_module(
        VoiceRecognitionModule,
        config={"model": "speechbrain/spkrec-ecapa-voxceleb"}
    )
    
    # Set up custom interruption handling
    maestro.interruption_handler = InterruptionHandler(
        threshold=0.2,
        acknowledgment_delay=50
    )
    
    # Start the system
    await maestro.start()
    
    # Access debug UI at http://localhost:8080

if __name__ == "__main__":
    asyncio.run(main())
```

## Success Criteria

1. **Developer Adoption**
   - 100+ GitHub stars in 3 months
   - Active community contributions
   - Multiple example implementations

2. **Technical Performance**
   - Consistent < 500ms latency
   - Zero memory leaks in 48-hour tests
   - Smooth handling of 10+ interruptions/minute

3. **Extensibility**
   - 5+ community-contributed modules
   - Integration with 3+ additional STT/TTS providers
   - Production deployment examples

## Risk Mitigation

1. **Pipecat Updates**
   - Pin Pipecat version initially
   - Maintain compatibility layer
   - Contribute improvements upstream

2. **Performance Bottlenecks**
   - Profile regularly
   - Implement caching strategically
   - Optimize hot paths

3. **Complexity Growth**
   - Maintain clear module boundaries
   - Regular refactoring cycles
   - Comprehensive test coverage