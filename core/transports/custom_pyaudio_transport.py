import asyncio
import pyaudio
import threading
import numpy as np
from collections import deque

from loguru import logger

from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, Frame, StartFrame, StopFrame
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import TransportParams

class CustomPyAudioInputTransport(BaseInputTransport):
    def __init__(self, params: TransportParams, sample_rate: int = 16000, channels: int = 1):
        super().__init__(params)
        self._sample_rate = sample_rate
        self._channels = channels
        self._audio = pyaudio.PyAudio()
        self._stream = None
        self._running = False
        self._thread = None
        self._frames_queue = asyncio.Queue()

    def _pyaudio_callback(self, in_data, frame_count, time_info, status):
        if self._running:
            self.get_event_loop().call_soon_threadsafe(self._frames_queue.put_nowait, in_data)
        return (in_data, pyaudio.paContinue)

    def _run_audio_thread(self):
        logger.debug("Starting PyAudio stream thread")
        self._stream = self._audio.open(
            format=pyaudio.paFloat32,
            channels=self._channels,
            rate=self._sample_rate,
            input=True,
            input_device_index=0,
            frames_per_buffer=256,
            stream_callback=self._pyaudio_callback,
        )
        self._stream.start_stream()
        logger.info("Custom PyAudio input stream started")
        while self._stream.is_active():
            pass
        logger.info("Custom PyAudio input stream finished")

    async def _push_frames_loop(self):
        while self._running:
            try:
                audio = await self._frames_queue.get()
                frame = InputAudioRawFrame(
                    audio=audio,
                    sample_rate=self._sample_rate,
                    num_channels=self._channels
                )
                await self.push_frame(frame)
                self._frames_queue.task_done()
            except asyncio.CancelledError:
                break

    async def start(self, frame: StartFrame):
        await super().start(frame)
        if self._running:
            return
        logger.info("Starting custom PyAudio input transport")
        self._running = True
        self._thread = threading.Thread(target=self._run_audio_thread, daemon=True)
        self._thread.start()
        self.create_task(self._push_frames_loop())
        await self.set_transport_ready(frame)

    async def stop(self, frame: StopFrame):
        await super().stop(frame)
        if not self._running:
            return
        logger.info("Stopping custom PyAudio input transport")
        self._running = False
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        self._audio.terminate()
        if self._thread:
            self._thread.join()
        logger.info("Custom PyAudio input transport stopped")


class CustomPyAudioOutputTransport(BaseOutputTransport):
    def __init__(self, params: TransportParams, sample_rate: int = 24000, channels: int = 1):
        super().__init__(params)
        self._sample_rate = sample_rate
        self._channels = channels
        self._audio = pyaudio.PyAudio()
        self._stream = None
        self._audio_queue = deque()
        self._min_buffer_size = int(sample_rate * 0.1)  # 100ms minimum buffer
        self._silence_frame = np.zeros(int(sample_rate * 0.02), dtype=np.float32).tobytes()  # 20ms silence

    async def start(self, frame: StartFrame):
        await super().start(frame)
        logger.info("Starting custom PyAudio output transport")
        self._stream = self._audio.open(
            format=pyaudio.paFloat32,
            channels=self._channels,
            rate=self._sample_rate,
            output=True,
        )
        self._stream.start_stream()
        await self.set_transport_ready(frame)

    async def stop(self, frame: StopFrame):
        await super().stop(frame)
        logger.info("Stopping custom PyAudio output transport")
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        self._audio.terminate()

    async def write_frame(self, frame: Frame):
        if isinstance(frame, OutputAudioRawFrame):
            try:
                # Simple direct write to restore audio
                if self._stream:
                    self._stream.write(frame.audio)
                    logger.debug(f"Wrote audio frame: {len(frame.audio)} bytes")
                
            except Exception as e:
                logger.warning(f"Audio write error: {e}")
                # Try to write silence to keep stream active
                try:
                    if self._stream:
                        self._stream.write(self._silence_frame)
                except:
                    pass
    
    def _write_with_protection(self):
        """Write audio with buffer underrun protection"""
        if not self._stream or not self._audio_queue:
            return
            
        try:
            # Get available space in PyAudio buffer
            available_frames = self._stream.get_write_available()
            
            # Only write if we have space and audio data
            while self._audio_queue and available_frames > 0:
                audio_data = self._audio_queue.popleft()
                
                # Calculate frame count for this audio data
                audio_np = np.frombuffer(audio_data, dtype=np.float32)
                frame_count = len(audio_np)
                
                if frame_count <= available_frames:
                    # Safe to write
                    self._stream.write(audio_data, num_frames=frame_count)
                    available_frames -= frame_count
                else:
                    # Split the audio data
                    safe_samples = available_frames
                    safe_audio = audio_np[:safe_samples].tobytes()
                    remaining_audio = audio_np[safe_samples:].tobytes()
                    
                    # Write safe portion
                    self._stream.write(safe_audio, num_frames=safe_samples)
                    
                    # Put remaining back in queue
                    self._audio_queue.appendleft(remaining_audio)
                    break
                    
        except Exception as e:
            logger.debug(f"Buffer underrun protection error: {e}")
            # Clear problematic audio from queue to prevent backup
            if len(self._audio_queue) > 10:  # Prevent excessive buildup
                self._audio_queue.clear()
                logger.warning("Cleared audio queue due to excessive buildup")
