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
            
            # Check if audio already has WAV header
            if len(frame.audio) >= 4:
                header = frame.audio[:4]
                if header == b'RIFF':
                    # Already a WAV file, return as-is
                    return frame.audio
            
            # Raw PCM data, add proper WAV header
            return self._add_wav_header(
                frame.audio, 
                frame.sample_rate, 
                frame.num_channels, 
                16  # 16-bit samples
            )
        
        # Return None for other frame types
        return None
    
    def _add_wav_header(self, pcm_data: bytes, sample_rate: int, num_channels: int, bits_per_sample: int) -> bytes:
        """Add WAV header to PCM data"""
        data_length = len(pcm_data)
        
        # Build WAV header
        header = bytearray(44)
        
        # "RIFF" chunk descriptor
        header[0:4] = b'RIFF'
        header[4:8] = (data_length + 36).to_bytes(4, 'little')  # file size - 8
        header[8:12] = b'WAVE'
        
        # "fmt " sub-chunk
        header[12:16] = b'fmt '
        header[16:20] = (16).to_bytes(4, 'little')  # subchunk size
        header[20:22] = (1).to_bytes(2, 'little')  # audio format (1 = PCM)
        header[22:24] = num_channels.to_bytes(2, 'little')
        header[24:28] = sample_rate.to_bytes(4, 'little')
        header[28:32] = (sample_rate * num_channels * (bits_per_sample // 8)).to_bytes(4, 'little')  # byte rate
        header[32:34] = (num_channels * (bits_per_sample // 8)).to_bytes(2, 'little')  # block align
        header[34:36] = bits_per_sample.to_bytes(2, 'little')
        
        # "data" sub-chunk
        header[36:40] = b'data'
        header[40:44] = data_length.to_bytes(4, 'little')
        
        return bytes(header) + pcm_data
        
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