# maestrocat/services/kokoro_tts.py
"""Kokoro TTS Service for Pipecat"""
import httpx
import time
from typing import AsyncGenerator, Optional
import logging

from pipecat.frames.frames import Frame, TTSAudioRawFrame, SystemFrame
from pipecat.services.tts_service import TTSService

logger = logging.getLogger(__name__)


class KokoroTTSService(TTSService):
    """
    Kokoro TTS integration for Pipecat
    Provides high-quality local text-to-speech
    """
    
    def __init__(
        self,
        *,
        base_url: str = "http://localhost:5000",
        voice: str = "af_bella",
        speed: float = 1.0,
        sample_rate: int = 16000,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self._base_url = base_url
        self._voice = voice
        self._speed = speed
        self._sample_rate = sample_rate
        
        self._client = httpx.AsyncClient(timeout=30.0)
        
    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """Generate speech from text"""
        
        try:
            # Start TTS (removed SystemFrame - not needed for basic TTS flow)
            
            # Prepare OpenAI-compatible request (matching Maestro format)
            request_data = {
                "model": "kokoro",
                "input": text,
                "voice": self._voice,
                "response_format": "pcm",
                "stream": True,
                "speed": self._speed,
                "volume_multiplier": 1.0
            }
            
            # Stream audio
            async with self._client.stream(
                "POST",
                f"{self._base_url}/v1/audio/speech",
                json=request_data
            ) as response:
                response.raise_for_status()
                
                async for chunk in response.aiter_bytes(chunk_size=256):
                    if chunk:
                        # Create audio frame
                        frame = TTSAudioRawFrame(
                            audio=chunk,
                            sample_rate=self._sample_rate,
                            num_channels=1
                        )
                        yield frame
                        
            # End TTS (removed SystemFrame - not needed for basic TTS flow)
            
        except Exception as e:
            logger.error(f"Kokoro TTS error: {e}")
            raise
            
    async def stop(self):
        """Cleanup HTTP client"""
        await super().stop()
        await self._client.aclose()
