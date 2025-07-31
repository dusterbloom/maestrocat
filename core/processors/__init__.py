# core/processors/__init__.py
"""MaestroCat processors module"""

from .interruption import InterruptionHandler, MetricsCollector
from .event_emitter import EventEmitter
from .module_loader import ModuleLoader
from .transcription_events import TranscriptionEventProcessor
from .config_handler import ConfigHandler
from .audio_tee import AudioTeeProcessor
from .speaker_context import SpeakerContextProcessor
from .speaker_name_manager import SpeakerNameManager
from .vad_event_bridge import VADEventBridge

__all__ = [
    'InterruptionHandler',
    'MetricsCollector', 
    'EventEmitter',
    'ModuleLoader',
    'TranscriptionEventProcessor',
    'ConfigHandler',
    'AudioTeeProcessor',
    'SpeakerContextProcessor',
    'SpeakerNameManager',
    'VADEventBridge'
]