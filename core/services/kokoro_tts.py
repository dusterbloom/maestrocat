# maestrocat/services/kokoro_tts.py
"""Kokoro TTS Service for Pipecat"""
import httpx
import time
import asyncio
import numpy as np
from typing import AsyncGenerator, Optional
import logging
import io
import wave

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
        sample_rate: int = 24000,  # Kokoro's native sample rate
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self._base_url = base_url
        self._voice = voice
        self._speed = speed
        self._sample_rate = sample_rate
        
        self._client = httpx.AsyncClient(timeout=30.0)
        self._current_request = None  # Track current request for cancellation
        self._audio_buffer = b""  # Buffer for accumulating audio chunks
        self._streaming_buffer = []  # Buffer for smooth audio streaming
        self._buffer_samples = int(self._sample_rate * 0.02)  # 20ms buffer for smoothing
        
    def _resample_audio(self, audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """Resample audio data from one sample rate to another"""
        if from_rate == to_rate:
            # Still need to convert to float32 format
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            return audio_np.tobytes()
            
        # Convert bytes to numpy array (assuming 16-bit PCM)
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Simple linear interpolation resampling
        original_length = len(audio_np)
        new_length = int(original_length * to_rate / from_rate)
        
        # Create new sample indices
        old_indices = np.linspace(0, original_length - 1, original_length)
        new_indices = np.linspace(0, original_length - 1, new_length)
        
        # Interpolate
        resampled = np.interp(new_indices, old_indices, audio_np)
        
        # Return as float32 for PyAudio
        return resampled.astype(np.float32).tobytes()
        
    def _extract_wav_data(self, wav_bytes: bytes) -> tuple[bytes, int]:
        """Extract PCM data and sample rate from WAV bytes"""
        try:
            with io.BytesIO(wav_bytes) as wav_io:
                with wave.open(wav_io, 'rb') as wav_file:
                    sample_rate = wav_file.getframerate()
                    pcm_data = wav_file.readframes(wav_file.getnframes())
                    return pcm_data, sample_rate
        except Exception as e:
            logger.warning(f"Failed to parse WAV data: {e}, treating as raw PCM")
            return wav_bytes, 24000  # Assume Kokoro's default
    
    def _add_to_streaming_buffer(self, audio_data: bytes):
        """Add audio data to streaming buffer for smooth playback"""
        # Convert to numpy float32 array
        audio_np = np.frombuffer(audio_data, dtype=np.float32)
        self._streaming_buffer.extend(audio_np)
        
    def _get_buffered_chunk(self, chunk_size: int) -> Optional[bytes]:
        """Get a chunk from the streaming buffer, return None if not enough data"""
        if len(self._streaming_buffer) < chunk_size:
            return None
            
        # Extract chunk
        chunk = np.array(self._streaming_buffer[:chunk_size], dtype=np.float32)
        self._streaming_buffer = self._streaming_buffer[chunk_size:]
        
        # Apply gentle fade in/out to reduce clicks
        fade_samples = min(64, chunk_size // 8)  # Small fade
        if fade_samples > 0:
            # Fade in at start
            fade_in = np.linspace(0, 1, fade_samples)
            chunk[:fade_samples] *= fade_in
            
            # Fade out at end  
            fade_out = np.linspace(1, 0, fade_samples)
            chunk[-fade_samples:] *= fade_out
            
        return chunk.tobytes()
        
    def _flush_streaming_buffer(self) -> Optional[bytes]:
        """Flush remaining audio from streaming buffer"""
        if not self._streaming_buffer:
            return None
            
        chunk = np.array(self._streaming_buffer, dtype=np.float32)
        self._streaming_buffer = []
        
        # Apply fade out to end
        fade_samples = min(64, len(chunk) // 4)
        if fade_samples > 0:
            fade_out = np.linspace(1, 0, fade_samples)
            chunk[-fade_samples:] *= fade_out
            
        return chunk.tobytes()
        
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
            
            # Prepare OpenAI-compatible request (PCM format for better streaming)
            request_data = {
                "model": "tts-1-hd",  # Use HD model for better quality
                "input": text,
                "voice": self._voice,
                "response_format": "wav",  # Request WAV to get proper headers
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
            
            # Clear buffers for new request
            self._audio_buffer = b""
            self._streaming_buffer = []
            wav_header_parsed = False
            kokoro_sample_rate = 24000  # Kokoro's native rate
            
            try:
                async with self._current_request as response:
                    response.raise_for_status()
                    
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            self._audio_buffer += chunk
                            
                            # Try to parse WAV header from accumulated buffer
                            if not wav_header_parsed and len(self._audio_buffer) > 44:
                                try:
                                    pcm_data, kokoro_sample_rate = self._extract_wav_data(self._audio_buffer)
                                    wav_header_parsed = True
                                    
                                    # Process the PCM data
                                    if pcm_data:
                                        # No resampling needed - keep native 24kHz
                                        frame = TTSAudioRawFrame(
                                            audio=pcm_data,
                                            sample_rate=kokoro_sample_rate,  # Use original rate
                                            num_channels=1
                                        )
                                        yield frame
                                        
                                    # Clear buffer after processing complete WAV
                                    self._audio_buffer = b""
                                except Exception as e:
                                    # If WAV parsing fails, continue accumulating
                                    logger.debug(f"WAV parsing not ready yet: {e}")
                                    pass
                            
                            # If we have a very large buffer but no WAV header, process as raw
                            elif len(self._audio_buffer) > 8192 and not wav_header_parsed:
                                logger.warning("Large buffer without WAV header, processing as raw PCM")
                                # Assume it's raw PCM at Kokoro's rate
                                if kokoro_sample_rate != self._sample_rate:
                                    processed_audio = self._resample_audio(self._audio_buffer, kokoro_sample_rate, self._sample_rate)
                                else:
                                    processed_audio = self._audio_buffer
                                
                                # Simple direct output for now to restore audio
                                frame = TTSAudioRawFrame(
                                    audio=self._audio_buffer,
                                    sample_rate=kokoro_sample_rate,  # Use original rate
                                    num_channels=1
                                )
                                yield frame
                                    
                                self._audio_buffer = b""
                    
                    # Process any remaining buffer data
                    if self._audio_buffer:
                        logger.info(f"Processing final buffer: {len(self._audio_buffer)} bytes")
                        try:
                            # Use raw buffer data at native sample rate
                            frame = TTSAudioRawFrame(
                                audio=self._audio_buffer,
                                sample_rate=kokoro_sample_rate,
                                num_channels=1
                            )
                            yield frame
                        except Exception as e:
                            logger.warning(f"Failed to process final buffer: {e}")
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
