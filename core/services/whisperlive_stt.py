# maestrocat/services/whisperlive_stt.py
"""WhisperLive STT Service for Pipecat"""
import asyncio
import json
import time
import numpy as np
from typing import AsyncGenerator, Optional, Dict, Any
import websockets
import logging

from pipecat.frames.frames import Frame, AudioRawFrame, InputAudioRawFrame, UserAudioRawFrame, TranscriptionFrame, SystemFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame
from pipecat.services.stt_service import STTService
from pipecat.processors.frame_processor import FrameDirection

logger = logging.getLogger(__name__)


class WhisperLiveSTTService(STTService):
    """
    WhisperLive WebSocket integration for Pipecat
    Provides real-time speech-to-text using Collabora's WhisperLive
    """
    
    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 9090,
        language: str = "en",
        translate: bool = False,
        model: str = "small",
        use_vad: bool = True,
        vad_threshold: float = 0.3,  # Lower threshold for more sensitive detection
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self._host = host
        self._port = port
        self._language = language
        self._translate = translate
        self._model = model
        self._use_vad = use_vad
        self._vad_threshold = vad_threshold
        
        self._websocket = None
        self._receive_task = None
        self._audio_buffer = bytearray()
        self._user_speaking = False
        self._client_uid = None
        self._processed_segments = set()  # Track processed segments to avoid duplicates
        self._max_segments = 100  # Limit memory usage
        
    async def start(self, frame: SystemFrame):
        """Start the STT service"""
        await super().start(frame)
        await self._connect()
        
    async def stop(self):
        """Stop the STT service"""
        await super().stop()
        
        if self._receive_task:
            self._receive_task.cancel()
            
        if self._websocket:
            await self._websocket.close()
            
    async def _connect(self):
        """Connect to WhisperLive server"""
        try:
            url = f"ws://{self._host}:{self._port}"
            self._websocket = await websockets.connect(url)
            
            # Send configuration
            self._client_uid = f"pipecat_{int(time.time() * 1000)}"
            config = {
                "uid": self._client_uid,
                "language": self._language,
                "task": "translate" if self._translate else "transcribe",
                "model": self._model,
                "use_vad": self._use_vad,
                "max_clients": 4,
                "max_connection_time": 600,
                "send_last_n_segments": 10,
                "no_speech_thresh": 0.45,
                "clip_audio": False,
                "same_output_threshold": 10
            }
            
            await self._websocket.send(json.dumps(config))
            logger.info(f"Connected to WhisperLive at {url}")
            
            # Start receive task
            self._receive_task = asyncio.create_task(self._receive_loop())
            
        except Exception as e:
            logger.error(f"Failed to connect to WhisperLive: {e}")
            raise
            
    async def _receive_loop(self):
        """Receive transcriptions from WhisperLive"""
        while self._websocket:
            try:
                message = await self._websocket.recv()
                
                if isinstance(message, str):
                    try:
                        data = json.loads(message)
                        # Only log SERVER_READY messages to reduce spam
                        if "message" in data and data.get("message") == "SERVER_READY":
                            logger.info(f"WhisperLive server ready")
                        await self._handle_message(data)
                    except json.JSONDecodeError:
                        # Plain text transcription
                        logger.info(f"WhisperLive PLAIN TEXT: {message}")
                        await self._handle_transcription(message, is_final=True)
                elif isinstance(message, bytes):
                    logger.info(f"WhisperLive BINARY message: {len(message)} bytes")
                else:
                    logger.info(f"WhisperLive UNKNOWN message type: {type(message)}: {message}")
                        
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WhisperLive connection closed")
                break
            except Exception as e:
                logger.error(f"Error in receive loop: {e}")
                break
            
    async def _handle_message(self, data: Dict[str, Any]):
        """Handle WhisperLive messages"""
        # Check if message is for our client
        if "uid" in data and data["uid"] != self._client_uid:
            logger.debug(f"Ignoring message for different client: {data['uid']}")
            return
            
        # Handle segments (main transcription format)
        if "segments" in data:
            segments = data["segments"]
            
            for segment in segments:
                text = segment.get("text", "").strip()
                completed = segment.get("completed", False)
                start = segment.get("start", "")
                end = segment.get("end", "")
                
                # Create unique segment identifier
                segment_id = f"{start}-{end}-{text}"
                
                if text and completed and segment_id not in self._processed_segments:
                    # Only process new completed segments
                    self._processed_segments.add(segment_id)
                    
                    # Limit memory usage by clearing old segments
                    if len(self._processed_segments) > self._max_segments:
                        # Keep only the most recent segments (simple cleanup)
                        self._processed_segments = set(list(self._processed_segments)[-50:])
                    
                    await self._handle_transcription(text, is_final=True)
                    
        # Handle legacy format (if any)
        elif "type" in data:
            msg_type = data.get("type", "")
            
            if msg_type == "transcript":
                text = data.get("text", "")
                if text:
                    await self._handle_transcription(text, is_final=True)
                    
            elif msg_type == "partial":
                text = data.get("text", "")
                if text:
                    await self._handle_transcription(text, is_final=False)
        
        # Handle other message types
        elif "message" in data:
            message = data.get("message", "")
            if message == "SERVER_READY":
                logger.info("WhisperLive server is ready")
            elif message in ["WAIT", "ERROR", "WARNING"]:
                logger.warning(f"WhisperLive server message: {message}")
                
    async def _handle_transcription(self, text: str, is_final: bool):
        """Handle transcription and create frames"""
        if not text:
            return
            
        # Filter out common Whisper hallucinations
        hallucination_phrases = [
            "thanks for watching",
            "see you in the next video",
            "don't forget to subscribe",
            "like and subscribe",
            "thank you for watching",
            "see you next time",
            "music playing",
            "applause",
            "laughter"
        ]
        
        text_lower = text.lower().strip()
        if any(phrase in text_lower for phrase in hallucination_phrases):
            logger.warning(f"🚫 Filtered hallucination: '{text}'")
            return
            
        # Only log final transcriptions to reduce noise
        if is_final:
            logger.info(f"Final transcription: '{text}'")
        
        # Create transcription frame
        frame = TranscriptionFrame(
            text=text,
            user_id="user",
            timestamp=time.time()
        )
        
        await self.push_frame(frame)
        if is_final:
            logger.info(f"→ Sent to LLM: '{text}'")
            
    async def _send_remaining_audio(self):
        """Send any remaining audio in buffer to WhisperLive"""
        if len(self._audio_buffer) > 0 and self._websocket and not self._websocket.closed:
            # Send remaining audio as final chunk
            chunk_data = bytes(self._audio_buffer)
            self._audio_buffer.clear()
            
            # Normalize the audio
            audio_samples = np.frombuffer(chunk_data, dtype=np.int16)
            if len(audio_samples) > 0:
                max_val = np.max(np.abs(audio_samples))
                if max_val > 16384:
                    audio_samples = (audio_samples * 16384 / max_val).astype(np.int16)
                    chunk = audio_samples.tobytes()
                    logger.info(f"Normalized final audio chunk from max {max_val} to 16384")
                else:
                    chunk = chunk_data
                    
                try:
                    await self._websocket.send(chunk)
                    logger.info(f"Sent final audio chunk: {len(chunk)} bytes")
                except Exception as e:
                    logger.error(f"Error sending final audio to WhisperLive: {e}")
            
    async def process_frame(self, frame: Frame, direction):
        """Process incoming frames"""
        # Log non-audio frames only
        if not isinstance(frame, (AudioRawFrame, InputAudioRawFrame, UserAudioRawFrame)):
            logger.debug(f"STT process_frame: {type(frame).__name__}, direction: {direction}")
        
        await super().process_frame(frame, direction)
        
        # Log speech events but don't filter audio based on them
        if isinstance(frame, UserStartedSpeakingFrame):
            logger.debug("User started speaking")
        elif isinstance(frame, UserStoppedSpeakingFrame):
            logger.debug("User stopped speaking")
        
        # Handle audio frames (check for both raw audio and input audio frames)
        if isinstance(frame, (AudioRawFrame, InputAudioRawFrame, UserAudioRawFrame)):
            # Check if audio contains actual data or just silence
            audio_samples = np.frombuffer(frame.audio, dtype=np.int16)
            max_amplitude = np.max(np.abs(audio_samples)) if len(audio_samples) > 0 else 0
            non_zero_samples = np.count_nonzero(audio_samples)
            
            # Only process audio with significant amplitude to avoid overwhelming WhisperLive
            silence_threshold = 2000  # Much higher threshold to prevent hallucinations
            
            if max_amplitude > silence_threshold:
                logger.debug(f"Audio: {len(frame.audio)} bytes, max_amplitude: {max_amplitude}, non_zero: {non_zero_samples}/{len(audio_samples)}")
                
                # Add audio to buffer only if it contains speech
                self._audio_buffer.extend(frame.audio)
                
                # Send chunks of audio to WhisperLive (larger chunks to reduce processing load)
                chunk_size = 16384   # 0.5 second of audio at 16kHz mono int16 - reduce chunk frequency
                while len(self._audio_buffer) >= chunk_size:
                    chunk_data = self._audio_buffer[:chunk_size]
                    self._audio_buffer = self._audio_buffer[chunk_size:]
                    
                    # Convert int16 PCM to Float32Array like maestro does
                    audio_samples_int16 = np.frombuffer(chunk_data, dtype=np.int16)
                    if len(audio_samples_int16) > 0:
                        # Convert int16 to float32 range [-1.0, 1.0] like maestro
                        audio_samples_float32 = audio_samples_int16.astype(np.float32) / 32768.0
                        chunk = audio_samples_float32.tobytes()
                        logger.debug(f"Converted audio chunk: {len(audio_samples_int16)} int16 -> {len(audio_samples_float32)} float32")
                    else:
                        chunk = bytes(chunk_data)
                    
                    if self._websocket and not self._websocket.closed:
                        try:
                            await self._websocket.send(chunk)
                            logger.debug(f"Sent audio chunk: {len(chunk)} bytes, buffer remaining: {len(self._audio_buffer)}")
                        except Exception as e:
                            logger.error(f"Error sending audio to WhisperLive: {e}")
                    else:
                        logger.warning(f"WebSocket not available for sending audio chunk")
            else:
                # For silence, just discard the audio to avoid overwhelming WhisperLive
                logger.debug(f"Silence detected (max_amplitude: {max_amplitude}), discarding audio")
                        
            # Pass the frame downstream
            await self.push_frame(frame, direction)
        else:
            logger.debug(f"Non-audio frame: {type(frame).__name__}")
            # Pass non-audio frames downstream
            await self.push_frame(frame, direction)
            
    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Process audio and generate transcription frames"""
        # This method is required by STTService but we handle audio in process_frame
        # and transcriptions in the receive loop
        yield  # Make this an async generator
