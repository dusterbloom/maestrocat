# maestrocat/services/kokoro_tts.py
"""Kokoro TTS Service for Pipecat"""
import httpx
import time
import asyncio
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
        sample_rate: int = 24000,  # Kokoro default is 24kHz
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self._base_url = base_url
        self._voice = voice
        self._speed = speed
        self._sample_rate = sample_rate
        
        self._client = httpx.AsyncClient(timeout=30.0)
        self._current_request = None  # Track current request for cancellation
        
    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """Generate speech from text"""
        
        try:
            # Cancel any existing request
            if self._current_request:
                logger.info("Cancelling previous TTS request")
                try:
                    await self._current_request.aclose()
                except:
                    pass
            
            # Prepare OpenAI-compatible request (WAV format for browser compatibility)
            request_data = {
                "model": "tts-1-hd",  # Use HD model for better quality
                "input": text,
                "voice": self._voice,
                "response_format": "wav",
                "stream": True,
                "speed": self._speed,
                "volume_multiplier": 1.0
            }
            
            # Stream audio
            self._current_request = self._client.stream(
                "POST",
                f"{self._base_url}/v1/audio/speech",
                json=request_data
            )
            
            try:
                async with self._current_request as response:
                    response.raise_for_status()
                    
                    async for chunk in response.aiter_bytes():  # Use natural chunk boundaries
                        if chunk:
                            # Create audio frame
                            frame = TTSAudioRawFrame(
                                audio=chunk,
                                sample_rate=self._sample_rate,
                                num_channels=1
                            )
                            yield frame
            finally:
                self._current_request = None
                        
        except asyncio.CancelledError:
            logger.info("TTS request cancelled")
            if self._current_request:
                try:
                    await self._current_request.aclose()
                except:
                    pass
                self._current_request = None
            raise
        except Exception as e:
            logger.error(f"Kokoro TTS error: {e}")
            if self._current_request:
                try:
                    await self._current_request.aclose()
                except:
                    pass
                self._current_request = None
            raise
            
    async def stop(self):
        """Cleanup HTTP client"""
        # Cancel any ongoing request
        if self._current_request:
            logger.info("Stopping TTS service, cancelling ongoing request")
            try:
                await self._current_request.aclose()
            except:
                pass
            self._current_request = None
            
        await super().stop()
        await self._client.aclose()
