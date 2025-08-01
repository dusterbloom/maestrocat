# Gemini Code Assistant Context

This document provides context for the Gemini code assistant to understand the MaestroCat project.

## Project Overview

MaestroCat is a Python-based, extensible voice agent framework built on the `pipecat` library. It is designed for ultra-low latency, local-first voice interactions. The project features a modular architecture that allows for hot-swappable components, including speech-to-text (STT), language models (LLM), and text-to-speech (TTS) services.

The system is designed to be platform-aware, with automatic detection and configuration for different operating systems, including macOS (with native services like MLX and CoreML), Linux, and Windows (via Docker).

## Key Features

- **Ultra-low latency:** Voice interactions with less than 500ms latency.
- **Smart Interruption Handling:** Manages conversation flow with context preservation.
- **Modular Architecture:** Key functionalities like voice recognition and memory are implemented as extensible modules.
- **Local-First:** Operates 100% locally, with no cloud dependencies.
- **Real-time Debug UI:** A web-based interface for monitoring, real-time configuration, and inspecting the event stream.
- **Platform Abstraction:** A unified launcher (`maestrocat.py`) automatically detects the platform and selects the optimal strategy (e.g., native macOS services vs. Docker-based services).
- **Hot-swappable Components:** Services and configurations can be changed without restarting the agent.

## Core Technologies

- **Backend:** Python, `pipecat-ai`
- **STT:** `whisper.cpp`, WhisperLive, MLX Whisper
- **LLM:** `Ollama` (e.g., Llama 3.2)
- **TTS:** Kokoro, Piper, macOS native TTS
- **UI:** HTML, CSS, JavaScript
- **Containerization:** Docker, Docker Compose

## Project Structure

- `maestrocat.py`: The main entry point and unified launcher.
- `core/`: Contains the core application logic.
  - `platform/`: Platform detection and strategy implementation (macOS, Docker, etc.).
  - `services/`: Wrappers for external services like STT, LLM, and TTS.
  - `processors/`: Custom `pipecat` processors for interruption, metrics, etc.
  - `modules/`: Extensible modules for features like voice recognition and memory.
- `config/`: YAML configuration files.
- `ui/`: Frontend code for the debug UI.
- `examples/`: Example agent implementations.
- `docker/`: Dockerfiles for containerized services.
- `tests/`: Unit and integration tests.

## How to Run

1.  **Install dependencies:**
    ```bash
    pip install "pipecat-ai[silero,daily]"
    pip install -e .
    ```

2.  **Start services (if using Docker):**
    ```bash
    docker-compose up -d
    ```

3.  **Run the agent:**
    ```bash
    python maestrocat.py
    ```
    The universal launcher will auto-detect the platform and run with the appropriate configuration.

4.  **Access the Debug UI:**
    Open `http://localhost:8080` in a web browser.

## How to Test

- **Run unit tests:**
  ```bash
  pytest
  ```
- **Run linting and formatting:**
  ```bash
  black maestrocat/
  ruff check maestrocat/
  ```

## Contribution Guidelines

- Follow the existing code style and conventions.
- Add tests for new features or bug fixes.
- Update documentation as needed.
- Submit pull requests to the `main` branch.