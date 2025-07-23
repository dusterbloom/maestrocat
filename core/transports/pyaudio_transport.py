# core/transports/pyaudio_transport.py
import asyncio
import pyaudio
from loguru import logger

from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, StartFrame, EndFrame
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport

# Audio configuration from your working script
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024  # PyAudio buffer size. We will get this many frames.
FORMAT = pyaudio.paFloat32 # Use Float32 for better quality and consistency
CHANNELS = 1

class PyAudioInputTransport(BaseInputTransport):
    def __init__(self):
        super().__init__()
        self._audio = pyaudio.PyAudio()
        self._stream = None

    def _audio_callback(self, in_data, frame_count, time_info, status):
        if status:
            logger.warning(f"PyAudio callback status: {status}")

        frame = InputAudioRawFrame(
            audio=in_data,
            sample_rate=SAMPLE_RATE,
            num_channels=CHANNELS
        )
        # Use the running event loop from the pipeline
        if self.get_event_loop() and self.get_event_loop().is_running():
            asyncio.run_coroutine_threadsafe(self.push_frame(frame), self.get_event_loop())
        return (None, pyaudio.paContinue)

    async def start(self, frame: StartFrame):
        logger.info("Starting custom PyAudio input transport...")
        try:
            # Try to use the pulse device (index 0) for WSL/Linux, as per your working script
            self._stream = self._audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=0,  # Use pulse device
                frames_per_buffer=CHUNK_SIZE,
                stream_callback=self._audio_callback
            )
            logger.info(f"Recording active with PulseAudio device (index=0)")
        except Exception as e:
            logger.error(f"Failed to open audio stream with index 0: {e}")
            logger.info("Trying default audio device...")
            try:
                # Fallback: Try default device
                self._stream = self._audio.open(
                    format=FORMAT,
                    channels=CHANNELS,
                    rate=SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=CHUNK_SIZE,
                    stream_callback=self._audio_callback
                )
                logger.info(f"Recording active with fallback default device")
            except Exception as e2:
                logger.error(f"Failed to open any audio stream: {e2}")
                raise

        self._stream.start_stream()
        logger.info("PyAudio input stream started.")

    async def stop(self, frame: EndFrame):
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        self._audio.terminate()
        logger.info("PyAudio input transport stopped.")

class PyAudioOutputTransport(BaseOutputTransport):
    def __init__(self):
        super().__init__()
        self._audio = pyaudio.PyAudio()
        self._stream = None

    async def start(self, frame: StartFrame):
        logger.info("Starting custom PyAudio output transport...")
        # The TTS service outputs at 16000 Hz, so we match that here.
        self._stream = self._audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            output=True
        )
        logger.info("PyAudio output stream started.")

    async def stop(self, frame: EndFrame):
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        self._audio.terminate()
        logger.info("PyAudio output transport stopped.")

    async def write_audio_frame(self, frame: OutputAudioRawFrame):
        if self._stream and frame.audio:
            self._stream.write(frame.audio)