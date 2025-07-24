# core/services/whispercpp_stt.py
"""Whisper.cpp STT Service for Pipecat - Native macOS support"""
import asyncio
import json
import time
import numpy as np
import subprocess
import tempfile
import os
from typing import AsyncGenerator, Optional, Dict, Any, List
import logging
import threading
import queue
from pathlib import Path

from pipecat.frames.frames import Frame, AudioRawFrame, InputAudioRawFrame, UserAudioRawFrame, TranscriptionFrame, SystemFrame
from pipecat.services.stt_service import STTService

logger = logging.getLogger(__name__)


class WhisperCppSTTService(STTService):
    """
    Whisper.cpp integration for Pipecat
    Provides real-time speech-to-text using whisper.cpp for native macOS performance
    """
    
    def __init__(
        self,
        *,
        model_path: str = None,
        model_size: str = "base",
        language: str = "en",
        translate: bool = False,
        use_vad: bool = True,
        vad_threshold: float = 0.5,
        sample_rate: int = 16000,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self._model_path = model_path
        self._model_size = model_size
        self._language = language
        self._translate = translate
        self._use_vad = use_vad
        self._vad_threshold = vad_threshold
        self._sample_rate = sample_rate
        
        self._audio_buffer = bytearray()
        self._processing_thread = None
        self._audio_queue = queue.Queue()
        self._running = False
        self._whisper_process = None
        self._min_audio_length = int(0.5 * sample_rate * 2)  # 0.5 seconds of audio
        
        # Whisper.cpp binary path - check common locations
        self._whisper_bin = self._find_whisper_binary()
        if not self._whisper_bin:
            raise RuntimeError("whisper.cpp binary not found. Please install with: brew install whisper-cpp")
            
        # Download model if needed
        self._ensure_model()
        
    def _find_whisper_binary(self) -> Optional[str]:
        """Find whisper.cpp binary in common locations"""
        # Check common binary names (whisper-cli is the new name)
        binary_names = ["whisper-cli", "whisper-cpp", "whisper"]
        
        # Check common installation paths
        base_paths = [
            "/opt/homebrew/bin",  # M1/M2 Macs
            "/usr/local/bin",     # Intel Macs
            "/usr/bin",           # System path
            os.path.expanduser("~/bin"),  # User bin
            "."                   # Current directory
        ]
        
        for binary_name in binary_names:
            for base_path in base_paths:
                path = os.path.join(base_path, binary_name)
                if os.path.exists(path) and os.access(path, os.X_OK):
                    logger.info(f"Found whisper.cpp at: {path}")
                    return path
                
            # Try to find with 'which'
            try:
                result = subprocess.run(["which", binary_name], capture_output=True, text=True)
                if result.returncode == 0:
                    path = result.stdout.strip()
                    logger.info(f"Found whisper.cpp via which: {path}")
                    return path
            except:
                continue
            
        return None
        
    def _ensure_model(self):
        """Ensure the Whisper model is downloaded"""
        if self._model_path and os.path.exists(self._model_path):
            return
            
        # Default model directory
        models_dir = os.path.expanduser("~/.cache/whisper")
        os.makedirs(models_dir, exist_ok=True)
        
        # Model filename based on size
        model_file = f"ggml-{self._model_size}.bin"
        self._model_path = os.path.join(models_dir, model_file)
        
        if os.path.exists(self._model_path):
            logger.info(f"Using existing model: {self._model_path}")
            return
            
        # Download model using whisper.cpp's download script
        logger.info(f"Downloading Whisper model: {self._model_size}")
        try:
            # Try to use the models download script
            whisper_dir = os.path.dirname(self._whisper_bin)
            download_script = os.path.join(whisper_dir, "..", "share", "whisper", "download-ggml-model.sh")
            
            if os.path.exists(download_script):
                subprocess.run([download_script, self._model_size], check=True)
            else:
                # Fallback: download directly
                model_urls = {
                    "tiny": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
                    "base": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
                    "small": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin",
                    "medium": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin",
                    "large": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin"
                }
                
                if self._model_size in model_urls:
                    import urllib.request
                    url = model_urls[self._model_size]
                    logger.info(f"Downloading from: {url}")
                    urllib.request.urlretrieve(url, self._model_path)
                    logger.info(f"Model downloaded to: {self._model_path}")
                else:
                    raise ValueError(f"Unknown model size: {self._model_size}")
                    
        except Exception as e:
            logger.error(f"Failed to download model: {e}")
            raise
            
    async def start(self, frame: SystemFrame):
        """Start the STT service"""
        await super().start(frame)
        self._running = True
        self._processing_thread = threading.Thread(target=self._processing_loop)
        self._processing_thread.start()
        logger.info(f"WhisperCpp STT service started with model: {self._model_path}")
        logger.info(f"Whisper binary: {self._whisper_bin}")
        logger.info(f"Language: {self._language}, Model size: {self._model_size}")
        
    async def stop(self):
        """Stop the STT service"""
        await super().stop()
        self._running = False
        
        # Signal processing thread to stop
        self._audio_queue.put(None)
        
        if self._processing_thread:
            self._processing_thread.join()
            
        logger.info("WhisperCpp STT service stopped")
        
    def _processing_loop(self):
        """Background thread for processing audio with whisper.cpp"""
        logger.info("WhisperCpp processing loop started")
        while self._running:
            try:
                # Get audio from queue with timeout
                logger.debug("Waiting for audio from queue...")
                audio_data = self._audio_queue.get(timeout=1.0)
                
                if audio_data is None:
                    logger.info("Received None, stopping processing loop")
                    break
                    
                logger.info(f"Processing audio chunk: {len(audio_data)} bytes")
                
                # Process with whisper.cpp
                transcription = self._process_audio_chunk(audio_data)
                
                if transcription:
                    logger.info(f"Got transcription: '{transcription}'")
                    # Use asyncio to push the transcription frame
                    asyncio.run_coroutine_threadsafe(
                        self._handle_transcription(transcription),
                        asyncio.get_event_loop()
                    )
                else:
                    logger.warning("No transcription returned from whisper.cpp")
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                break
        logger.info("WhisperCpp processing loop ended")
    def _process_audio_chunk(self, audio_data: bytes) -> Optional[str]:
        """Process audio chunk with whisper.cpp"""
        try:
            # Create temporary WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name
                
                # Convert raw audio to WAV format
                self._write_wav(temp_file, audio_data)
                
            # Run whisper.cpp (updated for whisper-cli)
            cmd = [
                self._whisper_bin,
                "-m", self._model_path,
                "-f", temp_path,
                "-l", self._language,
                "--no-timestamps",
                "--print-colors", "false",
                "--print-progress", "false",
                "--no-prints",  # Only output the transcription
                "--threads", "4",
                "--processors", "1"
            ]
            
            if self._translate:
                cmd.append("--translate")
                
            # Add VAD options if enabled (updated syntax)
            if self._use_vad:
                cmd.extend(["--vad"])
                cmd.extend(["--vad-threshold", str(self._vad_threshold)])
                
            logger.info(f"Running whisper.cpp command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Clean up temp file
            os.unlink(temp_path)
            
            logger.info(f"Whisper.cpp exit code: {result.returncode}")
            if result.stderr:
                logger.warning(f"Whisper.cpp stderr: {result.stderr}")
            if result.stdout:
                logger.info(f"Whisper.cpp stdout: {result.stdout}")
            
            if result.returncode == 0:
                # Extract transcription from output
                transcription = result.stdout.strip()
                
                # Filter out empty or noise transcriptions
                if transcription and len(transcription) > 1:
                    # Remove common Whisper artifacts
                    artifacts = ["[BLANK_AUDIO]", "[MUSIC]", "[APPLAUSE]", "[LAUGHTER]"]
                    for artifact in artifacts:
                        transcription = transcription.replace(artifact, "")
                        
                    transcription = transcription.strip()
                    if transcription:
                        return transcription
                        
            else:
                logger.error(f"Whisper.cpp error: {result.stderr}")
                
        except Exception as e:
            logger.error(f"Error processing audio chunk: {e}")
            
        return None
        
    def _write_wav(self, file, audio_data: bytes):
        """Write WAV header and audio data"""
        import struct
        
        # WAV file header
        sample_rate = self._sample_rate
        num_channels = 1
        bits_per_sample = 16
        
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        
        # Write RIFF header
        file.write(b'RIFF')
        file.write(struct.pack('<I', 36 + len(audio_data)))
        file.write(b'WAVE')
        
        # Write fmt chunk
        file.write(b'fmt ')
        file.write(struct.pack('<I', 16))  # fmt chunk size
        file.write(struct.pack('<H', 1))   # PCM format
        file.write(struct.pack('<H', num_channels))
        file.write(struct.pack('<I', sample_rate))
        file.write(struct.pack('<I', byte_rate))
        file.write(struct.pack('<H', block_align))
        file.write(struct.pack('<H', bits_per_sample))
        
        # Write data chunk
        file.write(b'data')
        file.write(struct.pack('<I', len(audio_data)))
        file.write(audio_data)
        
    async def _handle_transcription(self, text: str):
        """Handle transcription and create frames"""
        if not text:
            return
            
        logger.info(f"Transcription: '{text}'")
        
        # Create transcription frame
        frame = TranscriptionFrame(
            text=text,
            user_id="user",
            timestamp=time.time()
        )
        
        await self.push_frame(frame)
        
    async def process_frame(self, frame: Frame, direction):
        """Process incoming frames"""
        await super().process_frame(frame, direction)
        
        # Handle audio frames
        if isinstance(frame, (AudioRawFrame, InputAudioRawFrame, UserAudioRawFrame)):
            # Add audio to buffer
            self._audio_buffer.extend(frame.audio)
            
            # Log audio frame details
            audio_samples = np.frombuffer(frame.audio, dtype=np.int16)
            max_amplitude = np.max(np.abs(audio_samples)) if len(audio_samples) > 0 else 0
            logger.debug(f"Audio frame: {len(frame.audio)} bytes, max_amplitude: {max_amplitude}")
            
            # Process in chunks to balance latency and accuracy
            chunk_size = int(1.0 * self._sample_rate * 2)  # 1 second chunks
            
            while len(self._audio_buffer) >= chunk_size:
                chunk_data = bytes(self._audio_buffer[:chunk_size])
                self._audio_buffer = self._audio_buffer[chunk_size:]
                
                # Check if audio has sufficient energy
                audio_samples = np.frombuffer(chunk_data, dtype=np.int16)
                max_amplitude = np.max(np.abs(audio_samples)) if len(audio_samples) > 0 else 0
                
                logger.info(f"Processing audio chunk: {len(chunk_data)} bytes, max_amplitude: {max_amplitude}")
                
                # Only process audio with significant amplitude
                if max_amplitude > 1000:  # Threshold for speech detection
                    logger.info(f"Audio chunk above threshold, adding to queue")
                    # Add to processing queue
                    self._audio_queue.put(chunk_data)
                else:
                    logger.debug(f"Audio chunk below threshold ({max_amplitude} <= 1000)")
                    
            # Pass the frame downstream
            await self.push_frame(frame, direction)
        else:
            # Pass non-audio frames downstream
            await self.push_frame(frame, direction)
            
    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Process audio and generate transcription frames"""
        # This method is required by STTService but we handle audio in process_frame
        yield  # Make this an async generator