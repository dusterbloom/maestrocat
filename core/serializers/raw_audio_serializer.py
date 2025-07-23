# core/serializers/raw_audio_serializer.py
"""Raw audio serializer for WhisperLive integration"""
import json
from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, TTSAudioRawFrame, Frame
from pipecat.serializers.base_serializer import FrameSerializer, FrameSerializerType

class RawAudioSerializer(FrameSerializer):
    """Serializer that handles raw PCM audio for WhisperLive"""
    
    def __init__(self):
        super().__init__()
    
    @property
    def type(self) -> FrameSerializerType:
        """Get the serialization type - binary for raw audio data"""
        return FrameSerializerType.BINARY
        
    async def serialize(self, frame: Frame) -> str | bytes | None:
        """Serialize frame to WebSocket message"""
        # Handle TTS audio output frames
        if isinstance(frame, (TTSAudioRawFrame, OutputAudioRawFrame)):
            # Return raw audio bytes for browser playback
            # The browser expects WAV format audio from Kokoro
            return frame.audio
        
        # Return None for other frame types
        return None
        
    async def deserialize(self, data: str | bytes) -> Frame | None:
        """Deserialize WebSocket message to frame"""
        # Handle binary audio data
        if isinstance(data, bytes):
            # Create InputAudioRawFrame from raw PCM data
            # WhisperLive sends 16kHz mono PCM audio
            return InputAudioRawFrame(
                audio=data,
                sample_rate=16000,
                num_channels=1
            )
        
        # Handle text messages (for control messages)
        if isinstance(data, str):
            try:
                # Try to parse as JSON
                message = json.loads(data)
                # Return None for now - could handle control messages here
                return None
            except json.JSONDecodeError:
                # Plain text message
                return None
                
        return None