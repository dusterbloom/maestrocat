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
