# core/services/macos_tts.py
"""macOS System TTS Service for Pipecat - Native macOS support"""
import asyncio
import time
import numpy as np
import subprocess
import tempfile
import os
from typing import AsyncGenerator, Optional, List
import logging
import threading
import queue

from pipecat.frames.frames import Frame, TTSAudioRawFrame, SystemFrame
from pipecat.services.tts_service import TTSService

logger = logging.getLogger(__name__)


class MacOSTTSService(TTSService):
    """
    macOS System TTS integration for Pipecat
    Provides text-to-speech using macOS's built-in speech synthesis
    """
    
    def __init__(
        self,
        *,
        voice: str = "Samantha",
        rate: int = 200,  # Words per minute
        volume: float = 0.8,
        sample_rate: int = 22050,  # macOS default for speech
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self._voice = voice
        self._rate = rate
        self._volume = volume
        self._sample_rate = sample_rate
        
        # Get available voices and validate
        self._available_voices = self._get_available_voices()
        if voice not in self._available_voices:
            logger.warning(f"Voice '{voice}' not available. Using 'Samantha' instead.")
            self._voice = "Samantha"
            
        logger.info(f"Using macOS voice: {self._voice}")
        
    def _get_available_voices(self) -> List[str]:
        """Get list of available macOS voices"""
        try:
            result = subprocess.run(['say', '-v', '?'], capture_output=True, text=True)
            if result.returncode == 0:
                voices = []
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        # Parse voice name (format: "Voice Name    lang    description")
                        voice_name = line.split()[0]
                        voices.append(voice_name)
                return voices
        except Exception as e:
            logger.error(f"Failed to get available voices: {e}")
            
        # Fallback to common voices
        return ["Samantha", "Alex", "Victoria", "Daniel", "Karen", "Moira", "Tessa"]
        
    async def _synthesize_to_file(self, text: str, output_path: str) -> bool:
        """Synthesize text to audio file using macOS 'say' command"""
        try:
            cmd = [
                'say',
                '-v', self._voice,
                '-r', str(self._rate),
                '-o', output_path,
                '--data-format=LEI16@22050',  # 16-bit linear PCM at 22050 Hz
                text
            ]
            
            # Run synthesis
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await result.communicate()
            
            if result.returncode == 0 and os.path.exists(output_path):
                return True
            else:
                if stderr:
                    logger.error(f"macOS TTS error: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to synthesize speech: {e}")
            return False
            
    def _load_audio_file(self, file_path: str) -> Optional[bytes]:
        """Load audio file and return raw PCM data"""
        try:
            # Use ffmpeg to convert to raw PCM if available
            if self._has_ffmpeg():
                return self._load_with_ffmpeg(file_path)
            else:
                # Fallback: assume the file is already in the right format
                with open(file_path, 'rb') as f:
                    return f.read()
                    
        except Exception as e:
            logger.error(f"Failed to load audio file: {e}")
            return None
            
    def _has_ffmpeg(self) -> bool:
        """Check if ffmpeg is available"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
            
    def _load_with_ffmpeg(self, file_path: str) -> Optional[bytes]:
        """Load audio file using ffmpeg"""
        try:
            cmd = [
                'ffmpeg',
                '-i', file_path,
                '-f', 's16le',  # 16-bit signed little endian
                '-ar', str(self._sample_rate),  # Sample rate
                '-ac', '1',  # Mono
                '-'  # Output to stdout
            ]
            
            result = subprocess.run(cmd, capture_output=True, check=True)
            return result.stdout
            
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg error: {e}")
            return None
            
    def _apply_volume(self, audio_data: bytes) -> bytes:
        """Apply volume adjustment to audio data"""
        if self._volume == 1.0:
            return audio_data
            
        try:
            # Convert to numpy array
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            
            # Apply volume
            audio_np *= self._volume
            
            # Clip to prevent overflow
            audio_np = np.clip(audio_np, -32768, 32767)
            
            # Convert back to int16
            return audio_np.astype(np.int16).tobytes()
            
        except Exception as e:
            logger.error(f"Failed to apply volume: {e}")
            return audio_data
            
    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """Generate speech from text"""
        
        if not text.strip():
            return
            
        try:
            # Create temporary file for audio output
            with tempfile.NamedTemporaryFile(suffix='.aiff', delete=False) as temp_file:
                temp_path = temp_file.name
                
            logger.info(f"Synthesizing: '{text}' with voice '{self._voice}'")
            
            # Synthesize speech
            success = await self._synthesize_to_file(text, temp_path)
            
            if not success:
                logger.error("Failed to synthesize speech")
                return
                
            # Load and process audio
            audio_data = self._load_audio_file(temp_path)
            
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except:
                pass
                
            if not audio_data:
                logger.error("Failed to load synthesized audio")
                return
                
            logger.info(f"Generated {len(audio_data)} bytes of audio")
            
            # Apply volume adjustment
            audio_data = self._apply_volume(audio_data)
            
            # Yield audio in chunks for streaming
            chunk_size = int(self._sample_rate * 0.1 * 2)  # 100ms chunks (2 bytes per sample)
            
            offset = 0
            while offset < len(audio_data):
                chunk = audio_data[offset:offset + chunk_size]
                
                if chunk:
                    frame = TTSAudioRawFrame(
                        audio=chunk,
                        sample_rate=self._sample_rate,
                        num_channels=1
                    )
                    yield frame
                    
                    # Small delay to control streaming rate
                    await asyncio.sleep(0.05)  # 50ms between chunks
                    
                offset += chunk_size
                
        except Exception as e:
            logger.error(f"macOS TTS error: {e}")
            raise


class MacOSPyTTSx3Service(TTSService):
    """
    Alternative macOS TTS using pyttsx3 library
    Requires: pip install pyttsx3 pyobjc
    """
    
    def __init__(
        self,
        *,
        voice_id: str = None,
        rate: int = 200,
        volume: float = 0.8,
        sample_rate: int = 22050,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self._voice_id = voice_id
        self._rate = rate
        self._volume = volume
        self._sample_rate = sample_rate
        
        # Import pyttsx3 (optional dependency)
        try:
            import pyttsx3
            self._pyttsx3 = pyttsx3
            self._engine = None
            self._setup_engine()
        except ImportError:
            raise ImportError("pyttsx3 is required for PyTTSx3Service. Install with: pip install pyttsx3 pyobjc")
            
    def _setup_engine(self):
        """Setup pyttsx3 engine"""
        try:
            self._engine = self._pyttsx3.init(driverName='nsss')  # macOS driver
            
            # Set properties
            self._engine.setProperty('rate', self._rate)
            self._engine.setProperty('volume', self._volume)
            
            # Set voice if specified
            if self._voice_id:
                voices = self._engine.getProperty('voices')
                for voice in voices:
                    if self._voice_id in voice.id or self._voice_id in voice.name:
                        self._engine.setProperty('voice', voice.id)
                        break
                        
            logger.info("pyttsx3 engine initialized")
            
        except Exception as e:
            logger.error(f"Failed to setup pyttsx3 engine: {e}")
            raise
            
    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """Generate speech from text using pyttsx3"""
        
        if not text.strip():
            return
            
        try:
            # Create temporary file for audio output
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
                
            logger.info(f"Synthesizing with pyttsx3: '{text}'")
            
            # Synthesize speech in thread (pyttsx3 is synchronous)
            def synthesize():
                self._engine.save_to_file(text, temp_path)
                self._engine.runAndWait()
                
            await asyncio.get_event_loop().run_in_executor(None, synthesize)
            
            # Load audio file
            if os.path.exists(temp_path):
                with open(temp_path, 'rb') as f:
                    audio_data = f.read()
                    
                # Clean up
                os.unlink(temp_path)
                
                if audio_data:
                    # Simple chunking for streaming
                    chunk_size = 4096
                    offset = 0
                    
                    while offset < len(audio_data):
                        chunk = audio_data[offset:offset + chunk_size]
                        
                        if chunk:
                            frame = TTSAudioRawFrame(
                                audio=chunk,
                                sample_rate=self._sample_rate,
                                num_channels=1
                            )
                            yield frame
                            
                            await asyncio.sleep(0.01)  # Small delay
                            
                        offset += chunk_size
            else:
                logger.error("pyttsx3 failed to create audio file")
                
        except Exception as e:
            logger.error(f"pyttsx3 TTS error: {e}")
            raise