"""macOS Real-time Audio Transport for Streaming STT"""
import asyncio
import logging
import threading
import time
from typing import Optional, Callable, Dict, Any
import numpy as np

from core.services.whispercpp_streaming_stt import WhisperCppStreamingSTTService

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    logger.warning("sounddevice not available. Install with: pip install sounddevice")


class MacOSStreamTransport:
    """
    Real-time audio transport for macOS using sounddevice.
    
    Provides continuous microphone input for streaming STT services.
    """
    
    def __init__(
        self,
        stt_service: WhisperCppStreamingSTTService,
        sample_rate: int = 16000,
        channels: int = 1,
        block_size: int = 512,
        device: Optional[int] = None,
        dtype: str = 'int16'
    ):
        if not SOUNDDEVICE_AVAILABLE:
            raise RuntimeError(
                "sounddevice is required for MacOSStreamTransport. "
                "Install with: pip install sounddevice"
            )
            
        self.stt_service = stt_service
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.device = device
        self.dtype = dtype
        
        # State management
        self._is_running = False
        self._stream = None
        self._thread = None
        
        # Audio processing
        self._audio_buffer = bytearray()
        self._buffer_lock = threading.Lock()
        
        # Statistics
        self._stats = {
            'total_frames': 0,
            'total_bytes': 0,
            'start_time': None,
            'last_activity': None
        }
        
        logger.info(
            f"Initialized MacOSStreamTransport: {sample_rate}Hz, "
            f"{channels}ch, {block_size} samples/block"
        )
        
    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: dict, status: str):
        """Callback for audio input stream"""
        if status:
            logger.warning(f"Audio callback status: {status}")
            
        if not self._is_running:
            return
            
        # Convert numpy array to bytes
        audio_bytes = indata.tobytes()
        
        # Update statistics
        with self._buffer_lock:
            self._stats['total_frames'] += frames
            self._stats['total_bytes'] += len(audio_bytes)
            self._stats['last_activity'] = time.time()
            
        # Send audio to STT service
        try:
            self.stt_service.write_audio(audio_bytes)
        except Exception as e:
            logger.error(f"Error writing audio to STT service: {e}")
            
    def _get_audio_devices(self) -> Dict[int, str]:
        """Get available audio input devices"""
        devices = {}
        try:
            device_list = sd.query_devices()
            for i, device in enumerate(device_list):
                if device['max_input_channels'] > 0:
                    devices[i] = device['name']
        except Exception as e:
            logger.error(f"Error querying audio devices: {e}")
        return devices
        
    def list_devices(self) -> Dict[int, str]:
        """List available audio input devices"""
        devices = self._get_audio_devices()
        logger.info("Available audio input devices:")
        for device_id, name in devices.items():
            logger.info(f"  {device_id}: {name}")
        return devices
        
    def start(self) -> bool:
        """Start the audio stream"""
        if self._is_running:
            logger.warning("Stream already running")
            return True
            
        try:
            # List devices if none specified
            if self.device is None:
                devices = self.list_devices()
                if devices:
                    self.device = list(devices.keys())[0]
                    logger.info(f"Using default device: {devices[self.device]}")
                    
            # Create audio stream
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                blocksize=self.block_size,
                device=self.device,
                callback=self._audio_callback,
                latency='low'
            )
            
            # Start streaming
            self._stream.start()
            self._is_running = True
            self._stats['start_time'] = time.time()
            
            logger.info("Audio stream started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start audio stream: {e}")
            return False
            
    def stop(self) -> bool:
        """Stop the audio stream"""
        if not self._is_running:
            logger.warning("Stream not running")
            return True
            
        try:
            self._is_running = False
            
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
                
            logger.info("Audio stream stopped")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping audio stream: {e}")
            return False
            
    def get_stats(self) -> Dict[str, Any]:
        """Get streaming statistics"""
        with self._buffer_lock:
            stats = self._stats.copy()
            if stats['start_time']:
                stats['duration'] = time.time() - stats['start_time']
                stats['avg_bytes_per_second'] = stats['total_bytes'] / stats['duration']
            return stats
            
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()


def start_mic_stream(
    stt_service: WhisperCppStreamingSTTService,
    sample_rate: int = 16000,
    block_size: int = 512,
    device: Optional[int] = None
) -> MacOSStreamTransport:
    """
    Convenience function to start microphone streaming.
    
    Args:
        stt_service: The streaming STT service instance
        sample_rate: Audio sample rate (default: 16000)
        block_size: Audio block size in samples (default: 512)
        device: Specific audio device ID (default: auto-select)
        
    Returns:
        MacOSStreamTransport instance
    """
    transport = MacOSStreamTransport(
        stt_service=stt_service,
        sample_rate=sample_rate,
        block_size=block_size,
        device=device
    )
    
    transport.start()
    return transport


class AsyncMacOSStreamTransport:
    """
    Async wrapper for MacOSStreamTransport for use with asyncio.
    """
    
    def __init__(self, *args, **kwargs):
        self._transport = MacOSStreamTransport(*args, **kwargs)
        self._loop = None
        
    async def start(self):
        """Start transport in async context"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._transport.start
        )
        
    async def stop(self):
        """Stop transport in async context"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._transport.stop
        )
        
    async def list_devices(self):
        """List devices in async context"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._transport.list_devices
        )
        
    def get_stats(self):
        """Get streaming statistics"""
        return self._transport.get_stats()