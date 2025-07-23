#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import pyaudio

from loguru import logger

from pipecat.frames.frames import StartFrame
from pipecat.transports.local.audio import (
    LocalAudioInputTransport,
    LocalAudioTransport,
    LocalAudioTransportParams,
)

class WSLAudioInputTransport(LocalAudioInputTransport):
    """
    A custom audio input transport for WSL that overrides the PyAudio stream
    parameters to match a known-working configuration.
    """

    async def start(self, frame: StartFrame):
        # This is a near-copy of the original start method, but with hardcoded
        # values for format and frames_per_buffer that are known to work on WSL.
        await super().start(frame)

        if self._in_stream:
            return

        logger.info("Starting WSL-specific audio input transport")

        self._sample_rate = self._params.audio_in_sample_rate or frame.audio_in_sample_rate

        # Try to use the PulseAudio device
        try:
            self._in_stream = self._py_audio.open(
                format=pyaudio.paFloat32,  # Use paFloat32 as per the working script
                channels=self._params.audio_in_channels,
                rate=self._sample_rate,
                frames_per_buffer=256,  # Use 256 as per the working script
                stream_callback=self._audio_in_callback,
                input=True,
                input_device_index=self._params.input_device_index,
            )
            logger.info(f"Recording active with PulseAudio device (index={self._params.input_device_index})")
        except Exception as e:
            logger.error(f"Failed to open audio stream with index {self._params.input_device_index}: {e}")
            logger.info("Trying default audio device...")
            try:
                # Fallback: Try default device
                self._in_stream = self._py_audio.open(
                    format=pyaudio.paFloat32,
                    channels=self._params.audio_in_channels,
                    rate=self._sample_rate,
                    frames_per_buffer=256,
                    stream_callback=self._audio_in_callback,
                    input=True
                )
                logger.info("Recording active with fallback default device")
            except Exception as e2:
                logger.error(f"Failed to open any audio stream: {e2}")
                raise

        self._in_stream.start_stream()

        await self.set_transport_ready(frame)


class WSLAudioTransport(LocalAudioTransport):
    """
    A custom LocalAudioTransport that uses the WSL-specific input transport.
    """

    def __init__(self, params: LocalAudioTransportParams):
        super().__init__(params)
        # We only need to override the input transport
        self._input = WSLAudioInputTransport(self._pyaudio, self._params)
