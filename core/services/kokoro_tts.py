# maestrocat/services/kokoro_tts.py
"""Kokoro TTS Service for Pipecat"""
import httpx
import time
from typing import AsyncGenerator, Optional
import logging

from pipecat.frames.frames import Frame, TTSAudioRawFrame, SystemFrame
from pipecat.services.ai_services import TTSService

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
            # Start TTS
            yield SystemFrame("tts_started", {
                "text": text,
                "voice": self._voice
            })
            
            # Prepare request
            request_data = {
                "text": text,
                "voice": self._voice,
                "speed": self._speed,
                "sample_rate": self._sample_rate,
                "format": "pcm",
                "streaming": True
            }
            
            # Stream audio
            async with self._client.stream(
                "POST",
                f"{self._base_url}/synthesize",
                json=request_data
            ) as response:
                response.raise_for_status()
                
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    if chunk:
                        # Create audio frame
                        frame = TTSAudioRawFrame(
                            audio=chunk,
                            sample_rate=self._sample_rate,
                            num_channels=1
                        )
                        yield frame
                        
            # End TTS
            yield SystemFrame("tts_stopped")
            
        except Exception as e:
            logger.error(f"Kokoro TTS error: {e}")
            raise
            
    async def stop(self):
        """Cleanup HTTP client"""
        await super().stop()
        await self._client.aclose()
