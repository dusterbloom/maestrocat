# maestrocat/modules/__init__.py
"""MaestroCat modules"""

from .voice_recognition import VoiceRecognitionModule
from .voice_recognition_lightweight import LightweightVoiceRecognition
from .voice_recognition_auto_enroll import AutoEnrollVoiceRecognition
from .memory import MemoryModule

__all__ = [
    "VoiceRecognitionModule",
    "LightweightVoiceRecognition",
    "AutoEnrollVoiceRecognition",
    "MemoryModule",
]