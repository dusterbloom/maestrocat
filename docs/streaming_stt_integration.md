#!/bin/bash
# MaestroCat Streaming STT Integration Guide

# MaestroCat Streaming STT Integration Guide

This guide explains how to integrate real-time streaming speech-to-text using whisper.cpp with MaestroCat.

## Overview

The streaming STT integration provides:
- **Real-time transcription** with continuous audio ingestion
- **Incremental updates** showing partial transcriptions as you speak
- **Low latency** processing using whisper.cpp's streaming mode
- **Non-blocking** operation that doesn't freeze the UI
- **Seamless integration** with existing pipecat pipeline

## Quick Start

### 1. Build whisper.cpp streaming binary

```bash
# Make build script executable and run
chmod +x build_whispercpp_stream.sh
./build_whispercpp_stream.sh
```

### 2. Download model (if needed)

```bash
# Create models directory
mkdir -p models

# Download base English model
wget https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin -P models/
```

### 3. Install dependencies

```bash
pip install sounddevice
```

### 4. Run streaming example

```bash
python examples/local_maestrocat_streaming.py
```

## Configuration

### Basic Configuration

Update `config/maestrocat_macos.yaml`:

```yaml
stt:
  service: "whispercpp_streaming"  # Use streaming mode
  model_path: "models/ggml-base.en.bin"
  language: "en"
  sample_rate: 16000
  block_size: 512
  threads: 6
```

### Advanced Configuration

```yaml
stt:
  service: "whispercpp_streaming"
  model_path: "models/ggml-base.en.bin"
  language: "en"
  sample_rate: 16000
  block_size: 512        # Audio chunk size (lower = more responsive)
  threads: 6             # CPU threads for whisper.cpp
  use_vad: true          # Voice Activity Detection
  vad_threshold: 0.5     # VAD sensitivity (0.0-1.0)
```

## Usage Examples

### Basic Streaming

```python
from core.services.whispercpp_streaming_stt import WhisperCppStreamingSTtService
from core.transports.macos_stream_transport import MacOSStreamTransport

# Create streaming STt service
stt = WhisperCppStreamingSTtService(
    model_path="models/ggml-base.en.bin",
    language="en"
)

# Create audio transport
transport = MacOSStreamTransport(
    stt_service=stt,
    sample_rate=16000,
    block_size=512
)

# Start streaming
transport.start()

# Run for 30 seconds
import time
time.sleep(30)

# Stop streaming
transport.stop()
```

### Pipeline Integration

```python
from pipecat.pipeline.pipeline import Pipeline
from core.services.whispercpp_streaming_stt import WhisperCppStreamingSttService

# Create streaming stt
stt = WhisperCppStreamingSttService(
    model_path="models/ggml-base.en.bin"
)

# Create pipeline
pipeline = Pipeline([
    stt,
    llm_service,
    tts_service
)

# Run pipeline
runner = PipelineRunner()
task = PipelineTask(pipeline)
runner.run(task)
```

## UI Integration

The UI automatically handles streaming transcription events:

- **Real-time display**: Shows partial transcriptions as you speak
- **Confidence indicators**: Visual feedback for transcription confidence
- **Smooth animations**: Character-by-character streaming updates
- **Interruption handling**: Properly handles voice interruptions

### Event Types

The UI responds to these streaming events:

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

The UI responds to these streaming events:

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

The UI responds to these streaming events:

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

### Event Types

- `transcription_partial`: Incremental transcription updates
- `transcription_final`: Completed transcription
- `interruption_detected`: Voice activity interruption

#