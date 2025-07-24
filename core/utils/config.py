# maestrocat/utils/config.py
"""Configuration management for MaestroCat"""
from typing import Dict, Any, Optional
from dataclasses import dataclass
import yaml
import os


@dataclass
class VADConfig:
    energy_threshold: float = 0.5
    min_speech_ms: int = 250
    pause_ms: int = 800
    

@dataclass 
class STTConfig:
    host: str = "localhost"
    port: int = 9090
    language: str = "en"
    translate: bool = False
    model: str = "small"
    use_vad: bool = True
    # macOS native service options
    service: str = "whisperlive"  # "whisperlive" or "whispercpp"
    model_size: str = "base"      # For whisper.cpp
    model_path: Optional[str] = None  # Custom model path
    sample_rate: int = 16000      # Audio sample rate
    vad_threshold: float = 0.5    # VAD threshold for whisper.cpp
    

@dataclass
class LLMConfig:
    base_url: str = "http://localhost:11434"
    model: str = "llama3.2:3b"
    temperature: float = 0.7
    max_tokens: int = 1000
    top_p: float = 0.9
    top_k: int = 40
    system_prompt: str = "You are a helpful AI assistant."
    

@dataclass
class TTSConfig:
    base_url: str = "http://localhost:5000"
    voice: str = "af_bella"
    speed: float = 1.0
    sample_rate: int = 24000
    # macOS native service options
    service: str = "kokoro"       # "kokoro", "macos", "pyttsx3"
    rate: int = 200              # Words per minute for macOS TTS
    volume: float = 0.8          # Volume for macOS TTS
    voice_id: Optional[str] = None  # For PyTTSx3
    

@dataclass
class InterruptionConfig:
    threshold: float = 0.2
    ack_delay: float = 0.05
    

class MaestroCatConfig:
    """Main configuration class"""
    
    def __init__(self, config_dict: Dict[str, Any]):
        self.vad = VADConfig(**config_dict.get("vad", {}))
        self.stt = STTConfig(**config_dict.get("stt", {}))
        self.llm = LLMConfig(**config_dict.get("llm", {}))
        self.tts = TTSConfig(**config_dict.get("tts", {}))
        self.interruption = InterruptionConfig(**config_dict.get("interruption", {}))
        self.modules = config_dict.get("modules", {})
        
        # Additional macOS-specific sections
        self.macos = config_dict.get("macos", {})
        self.development = config_dict.get("development", {})
        self.production = config_dict.get("production", {})
        
    @classmethod
    def from_file(cls, file_path: str) -> "MaestroCatConfig":
        """Load configuration from YAML file"""
        with open(file_path, "r") as f:
            config_dict = yaml.safe_load(f)
        return cls(config_dict)
        
    @classmethod
    def from_env(cls) -> "MaestroCatConfig":
        """Create configuration from environment variables"""
        config_dict = {
            "stt": {
                "host": os.getenv("WHISPERLIVE_HOST", "localhost"),
                "port": int(os.getenv("WHISPERLIVE_PORT", "9090")),
            },
            "llm": {
                "base_url": os.getenv("OLLAMA_URL", "http://localhost:11434"),
                "model": os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            },
            "tts": {
                "base_url": os.getenv("KOKORO_URL", "http://localhost:5000"),
                "voice": os.getenv("KOKORO_VOICE", "af_bella"),
            }
        }
        return cls(config_dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "vad": {
                "energy_threshold": self.vad.energy_threshold,
                "min_speech_ms": self.vad.min_speech_ms,
                "pause_ms": self.vad.pause_ms
            },
            "stt": {
                "host": self.stt.host,
                "port": self.stt.port,
                "language": self.stt.language,
                "translate": self.stt.translate,
                "model": self.stt.model,
                "use_vad": self.stt.use_vad,
                "service": self.stt.service,
                "model_size": self.stt.model_size,
                "sample_rate": self.stt.sample_rate
            },
            "llm": {
                "base_url": self.llm.base_url,
                "model": self.llm.model,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
                "system_prompt": self.llm.system_prompt
            },
            "tts": {
                "base_url": self.tts.base_url,
                "voice": self.tts.voice,
                "speed": self.tts.speed,
                "sample_rate": self.tts.sample_rate,
                "service": self.tts.service,
                "rate": self.tts.rate,
                "volume": self.tts.volume
            },
            "interruption": {
                "threshold": self.interruption.threshold,
                "ack_delay": self.interruption.ack_delay
            },
            "modules": self.modules,
            "macos": self.macos,
            "development": self.development,
            "production": self.production
        }
