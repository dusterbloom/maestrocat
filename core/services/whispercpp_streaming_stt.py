"""Whisper.cpp Streaming STT Service for Pipecat - Real-time transcription"""
import asyncio
import json
import time
import logging
import threading
import subprocess
import os
from typing import AsyncGenerator, Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from pipecat.frames.frames import Frame, TranscriptionFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame
from pipecat.services.stt_service import STTService

logger = logging.getLogger(__name__)


class TranscriptionState(Enum):
    """States for streaming transcription"""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    FINALIZING = "finalizing"


@dataclass
class StreamingTranscription:
    """Represents a streaming transcription result"""
    text: str
    is_partial: bool
    confidence: float
    timestamp: float
    duration: float


@dataclass
class TranscriptionSegment:
    """Represents a single segment from whisper-stream"""
    text: str
    start_time: float
    end_time: float
    confidence: float
    timestamp: float


class UtteranceBoundaryDetector:
    """Detects utterance boundaries from whisper-stream segments using timestamp analysis"""
    
    def __init__(
        self,
        silence_threshold_ms: float = 500.0,  # Gap indicating utterance boundary
        completion_timeout_ms: float = 2000.0,  # Max time to wait for more segments
        min_utterance_length: int = 2  # Minimum characters for valid utterance
    ):
        self.silence_threshold = silence_threshold_ms / 1000.0  # Convert to seconds
        self.completion_timeout = completion_timeout_ms / 1000.0
        self.min_utterance_length = min_utterance_length
        
        # Segment buffering
        self._segment_buffer: List[TranscriptionSegment] = []
        self._last_segment_time = 0.0
        self._transcription_session_id = None
        self._session_start_time = 0.0
        
    def add_segment(self, segment: TranscriptionSegment, session_id: str = None) -> Optional[str]:
        """
        Add a segment and return complete utterance if boundary detected.
        
        Args:
            segment: The transcription segment to add
            session_id: Optional session identifier from whisper-stream
            
        Returns:
            Complete utterance text if boundary detected, None otherwise
        """
        current_time = time.time()
        
        # Detect new transcription session
        if session_id and session_id != self._transcription_session_id:
            # New session started - emit any pending utterance
            complete_utterance = self._finalize_current_utterance()
            self._start_new_session(session_id, current_time)
            self._segment_buffer.append(segment)
            return complete_utterance
            
        # Check for silence gap (utterance boundary)
        if self._segment_buffer and segment.start_time > self._segment_buffer[-1].end_time + self.silence_threshold:
            # Silence gap detected - finalize current utterance and start new one
            complete_utterance = self._finalize_current_utterance()
            self._segment_buffer = [segment]
            self._last_segment_time = current_time
            return complete_utterance
            
        # Add to current utterance buffer
        self._segment_buffer.append(segment)
        self._last_segment_time = current_time
        return None
        
    def session_ended(self, session_id: str = None) -> Optional[str]:
        """
        Mark transcription session as ended and return complete utterance.
        
        Args:
            session_id: Session identifier that ended
            
        Returns:
            Complete utterance text if any segments buffered
        """
        if session_id == self._transcription_session_id or session_id is None:
            return self._finalize_current_utterance()
        return None
        
    def check_timeout(self) -> Optional[str]:
        """
        Check if current utterance has timed out and should be finalized.
        
        Returns:
            Complete utterance text if timeout occurred, None otherwise
        """
        if not self._segment_buffer:
            return None
            
        current_time = time.time()
        if current_time - self._last_segment_time > self.completion_timeout:
            return self._finalize_current_utterance()
            
        return None
        
    def _start_new_session(self, session_id: str, current_time: float):
        """Start a new transcription session"""
        self._transcription_session_id = session_id
        self._session_start_time = current_time
        self._segment_buffer = []
        
    def _finalize_current_utterance(self) -> Optional[str]:
        """Finalize the current utterance and return the complete text"""
        if not self._segment_buffer:
            return None
            
        # Sort segments by start time to ensure proper order
        sorted_segments = sorted(self._segment_buffer, key=lambda x: x.start_time)
        
        # Merge overlapping or adjacent segments
        merged_text = self._merge_segments(sorted_segments)
        
        # Clear buffer
        self._segment_buffer = []
        self._transcription_session_id = None
        
        # Return complete utterance if meets minimum length
        if len(merged_text.strip()) >= self.min_utterance_length:
            return merged_text.strip()
            
        return None
        
    def _merge_segments(self, segments: List[TranscriptionSegment]) -> str:
        """Merges a list of segments into a single utterance string by joining them."""
        if not segments:
            return ""
        # A simple join is more robust than complex overlap logic.
        # The stream tool often refines the transcript, and the sequence of segments
        # represents the evolution of the transcription. Joining them is a safe
        # and effective way to form the complete utterance.
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip())


class WhisperCppStreamingSTTService(STTService):
    """
    Real-time streaming STT using whisper.cpp stream binary.
    
    Provides continuous speech-to-text with incremental results,
    designed for low-latency real-time applications.
    """
    
    def __init__(
        self,
        *,
        model_path: str = None,
        model_size: str = "base",
        language: str = "en",
        translate: bool = False,
        sample_rate: int = 16000,
        channels: int = 1,
        block_size: int = 512,
        max_latency_ms: int = 200,
        step_ms: int = 500,  # Reduced from 2500ms for lower latency
        length_ms: int = 10000,  # Increased from 3000ms for more context
        keep_ms: int = 2000,  # Increased from 100ms for better context retention
        voice_threshold: float = 0.8,
        threads: int = 3,  # Reduced from 6 - better thermal management on MacBook
        event_emitter=None,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self._model_path = model_path
        self._model_size = model_size
        self._language = language
        self._translate = translate
        self._sample_rate = sample_rate
        self._channels = channels
        self._block_size = block_size
        self._max_latency_ms = max_latency_ms
        self._step_ms = step_ms
        self._length_ms = length_ms
        self._keep_ms = keep_ms
        self._voice_threshold = voice_threshold
        self._threads = threads
        self._event_emitter = event_emitter
        
        # State management
        self._state = TranscriptionState.IDLE
        self._current_transcription = ""
        self._last_partial_time = 0
        self._is_running = False
        
        # Deduplication tracking
        self._last_emitted_text = ""
        self._last_emission_time = 0.0
        self._dedup_time_window = 2.0  # 2 seconds window for deduplication
        
        # Utterance boundary detection
        self._boundary_detector = UtteranceBoundaryDetector(
            silence_threshold_ms=800.0,   # 800ms gap indicates utterance boundary (reduced from 1200ms)
            completion_timeout_ms=1500.0, # 1.5s timeout for incomplete utterances (reduced from 2.5s)
            min_utterance_length=3        # Minimum 3 characters for valid utterance
        )
        
        # VAD-aware transcription control
        self._user_is_speaking = False
        self._user_stopped_time = 0.0
        self._vad_grace_period = 1.0  # Accept transcriptions for 1s after user stops speaking
        self._speech_session_active = False
        
        # Legacy sliding window overlap handling has been removed as the UtteranceBoundaryDetector
        # with timestamp analysis provides more accurate utterance boundary detection.
        
        # Process management
        self._whisper_process = None
        self._stdout_thread = None
        self._stderr_thread = None
        
        # Thread-safe buffers
        self._audio_buffer = bytearray()
        self._buffer_lock = threading.Lock()
        
        # Event loop for thread-safe async calls
        self._loop = None
        
        # Timeout checker task
        self._timeout_checker_task = None
        self._timeout_check_interval = 1.0  # Check every second
        
        # Adaptive processing for thermal management
        self._consecutive_silence_count = 0
        self._high_activity_mode = False
        
        # Language change handling
        self._original_language = language  # Store original for comparison
        self._config_language = language  # Track config language separately
        self._needs_restart = False  # Flag to track if restart is needed
        
        # Audio feedback prevention
        self._recent_tts_texts = []  # Store recent TTS outputs to prevent feedback
        self._tts_buffer_duration = 10.0  # Keep TTS texts for 10 seconds
        self._similarity_threshold = 0.85  # Threshold for detecting TTS echo
        self._paused_for_tts = False  # Track if paused due to TTS playback
        
        # Process resource management
        self._idle_timeout = 30.0  # Stop process after 30s of no activity
        self._last_activity_time = 0.0
        
        # Find whisper.cpp stream binary
        self._stream_binary = self._find_stream_binary()
        if not self._stream_binary:
            raise RuntimeError(
                "whisper.cpp stream binary not found. "
                "Please run: ./build_whispercpp_stream.sh"
            )
        
        # Ensure model exists
        self._ensure_model()
        
        # Validate language setting
        if self._language and self._language.lower() == "auto":
            logger.warning("\u26a0\ufe0f  WhisperCpp stream tool doesn't support 'auto' language detection")
            logger.warning("\u26a0\ufe0f  Please specify a language code (e.g., 'en', 'it', 'es', 'fr', etc.)")
            logger.warning("\u26a0\ufe0f  Defaulting to English ('en') for now")
            self._language = "en"
        
        # Subscribe to config change events if event emitter is available
        if self._event_emitter:
            self._event_emitter.subscribe("config_change", self._handle_config_change)
            self._event_emitter.subscribe("tts_start", self._handle_tts_start)
            self._event_emitter.subscribe("tts_complete", self._handle_tts_complete)
            logger.info("🔔 Subscribed to config_change and TTS events for feedback prevention")
        
        # Pre-loading state
        self._is_preloaded = False
        self._preload_task = None
        self._initialization_complete = False
        self._model_load_complete = False
        
        logger.info(f"Initialized WhisperCppStreamingSTTService with model: {self._model_path}")
        logger.info(f"🌍 Initial language setting: '{self._language}', Auto-detect: {self._language == 'auto'}")
        
    def _find_stream_binary(self) -> Optional[str]:
        """Find whisper.cpp stream binary in common locations"""
        search_paths = [
            "./bin/whisper-stream",
            "./bin/stream", 
            "./whisper.cpp/build/bin/whisper-stream",
            "./whisper.cpp/stream",
            "/opt/homebrew/bin/whisper-stream",
            "/opt/homebrew/bin/stream",
            "/usr/local/bin/whisper-stream",
            "/usr/local/bin/stream",
            os.path.expanduser("~/bin/whisper-stream"),
            os.path.expanduser("~/bin/stream"),
            "."
        ]
        
        for path in search_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                logger.info(f"Found whisper.cpp stream binary at: {path}")
                return path
                
        # Try which command
        try:
            result = subprocess.run(["which", "stream"], capture_output=True, text=True)
            if result.returncode == 0:
                path = result.stdout.strip()
                logger.info(f"Found stream binary via which: {path}")
                return path
        except:
            pass
            
        return None
        
    def _ensure_model(self):
        """Ensure the Whisper model is available, prioritizing quantized models."""
        if self._model_path and os.path.exists(self._model_path):
            return

        # Prioritized list of quantization suffixes from most to least preferred
        quantization_suffixes = [
            "-q5_1", "-q5_0", "-q8_0", "-q4_1", "-q4_0", ""  # "" for the unquantized model
        ]

        # For streaming, prefer smaller models
        if self._model_size not in ["tiny", "base", "small"]:
            logger.warning(f"⚠️  Model size '{self._model_size}' may be too large for streaming, using 'base' instead")
            self._model_size = "base"

        search_dirs = [
            "./mlx_models",
            "./models",
            "./whisper.cpp/models",
            os.path.expanduser("~/.cache/whisper"),
            os.path.expanduser("~/models"),
        ]

        for suffix in quantization_suffixes:
            model_file = f"ggml-{self._model_size}{suffix}.bin"
            for models_dir in search_dirs:
                model_path = os.path.join(models_dir, model_file)
                if os.path.exists(model_path):
                    self._model_path = model_path
                    logger.info(f"✅ Found optimal model: {self._model_path}")
                    return

        # Fallback to a default path if no model is found
        default_model_file = f"ggml-{self._model_size}.bin"
        default_dir = os.path.expanduser("~/.cache/whisper")
        os.makedirs(default_dir, exist_ok=True)
        self._model_path = os.path.join(default_dir, default_model_file)

        logger.warning(
            f"Could not find an optimal model in {search_dirs}. "
            f"Using fallback path: {self._model_path}. "
            f"For best performance, download a quantized model (e.g., ggml-base-q5_1.bin)."
        )
            
    async def _preload_model(self):
        """Pre-load the Whisper.cpp model by starting the streaming process early"""
        if self._is_preloaded:
            logger.info("📋 Whisper.cpp model already pre-loaded")
            return
        
        logger.info("🚀 Pre-loading Whisper.cpp streaming model...")
        
        try:
            # Reset initialization tracking flags
            self._initialization_complete = False
            self._model_load_complete = False
            
            # Start the streaming process without waiting for WebSocket connection
            self._start_streaming_process()
            
            # Wait for proper initialization completion
            max_wait = 15.0  # Increased timeout for thorough initialization
            wait_interval = 0.1
            total_waited = 0.0
            
            logger.info("⏳ Waiting for model initialization to complete...")
            
            while total_waited < max_wait:
                if not (self._whisper_process and self._whisper_process.poll() is None and self._is_running):
                    logger.error("❌ Whisper process died during pre-loading")
                    return
                
                # Check if initialization is truly complete
                if self._initialization_complete and self._model_load_complete:
                    # Give it a small additional buffer to ensure everything is settled
                    await asyncio.sleep(0.5)
                    self._is_preloaded = True
                    logger.info("✅ Whisper.cpp model pre-loaded and ready for instant transcription")
                    return
                
                await asyncio.sleep(wait_interval)
                total_waited += wait_interval
            
            # Fallback: if we can't detect completion but process is running, assume ready
            if self._whisper_process and self._whisper_process.poll() is None and self._is_running:
                logger.warning("⚠️  Could not detect initialization completion, but process is running - assuming ready")
                self._is_preloaded = True
            else:
                logger.error("❌ Whisper.cpp pre-loading failed - process not running or timed out")
            
        except Exception as e:
            logger.error(f"❌ Failed to pre-load Whisper.cpp model: {e}")
            
    def _start_streaming_process(self):
        """Start the whisper.cpp streaming process"""
        if self._whisper_process and self._whisper_process.poll() is None:
            logger.debug("🔄 Whisper.cpp process already running, skipping start")
            return
            
        # Reset initialization tracking flags for new process
        self._initialization_complete = False
        self._model_load_complete = False
            
        cmd = [
            self._stream_binary,
            "-m", self._model_path,
            "-t", str(self._threads),  # Configurable thread count
            "--step", str(self._step_ms),  # Fixed time steps to eliminate overlap
            "--length", str(self._length_ms),  # Configurable context window
            "--keep", str(self._keep_ms),  # Configurable context retention
            "-vth", str(self._voice_threshold),  # Configurable voice activity threshold
            "-fth", "200.0",  # Higher frequency threshold to filter noise
            "-c", "-1",  # Use default capture device
            "-nf",  # No temperature fallback to reduce hallucinations
        ]
        
        # Handle language setting - always specify a language (stream tool doesn't support auto)
        if self._language and self._language.lower() == "auto":
            # Stream tool doesn't support auto detection - default to English
            cmd.extend(["-l", "en"])
            logger.warning("⚠️  Stream tool doesn't support 'auto' - defaulting to English")
            logger.warning("⚠️  For multilingual support, specify a language explicitly")
        else:
            cmd.extend(["-l", self._language])
            logger.info(f"🌍 Using explicit language: {self._language}")
        
        # Add keep-context flag for better language consistency (based on whisper-stream help)
        if not self._translate and self._language and self._language.lower() not in ["en", "auto"]:
            cmd.append("-kc")  # Keep context between chunks for consistency
            logger.info("🔗 Added --keep-context flag for language consistency")
        
        # Debug: Log language and translate settings for troubleshooting
        logger.info(f"🌍 Language setting: '{self._language}', Translate: {self._translate}")
        logger.info(f"📁 Model path: '{self._model_path}'")
        
        # Check if using English-only model (major cause of forced translation)
        if self._model_path and "base.en.bin" in self._model_path:
            logger.warning("⚠️  WARNING: Using English-only model (.en.bin) - this will force translation!")
            logger.warning("⚠️  Solution: Use multilingual model (ggml-base.bin) instead")
        
        # if self._translate:
        #     cmd.append("-tr")
        #     logger.info("🔄 Translation ENABLED - will translate to English")
        # else:
        #     logger.info(f"🚫 Translation DISABLED - should stay in {self._language}")
            
        logger.info(f"Starting whisper.cpp stream: {' '.join(cmd)}")
        
        try:
            self._whisper_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,  # Line buffering for real-time output
                universal_newlines=True
            )
            
            # Check if process started successfully
            logger.info(f"Process started with PID: {self._whisper_process.pid}")
            logger.info(f"Process poll result: {self._whisper_process.poll()}")
            logger.info(f"Stdout readable: {self._whisper_process.stdout.readable()}")
            logger.info(f"Stderr readable: {self._whisper_process.stderr.readable()}")
            
            # Start output reading threads
            self._stdout_thread = threading.Thread(
                target=self._read_stdout,
                daemon=True
            )
            self._stderr_thread = threading.Thread(
                target=self._read_stderr,
                daemon=True
            )
            
            self._stdout_thread.start()
            self._stderr_thread.start()
            
            self._is_running = True
            logger.info("Whisper.cpp streaming process started successfully")
            logger.info(f"Process PID: {self._whisper_process.pid}")
            logger.info("Stdout and stderr reader threads started")
            
            # Give the process a moment to fully initialize and wait for the ready message
            import time
            time.sleep(1.0)  # Allow more time for full initialization
            logger.info(f"Process still running: {self._whisper_process.poll() is None}")
            
            # The process should print "[Start speaking]" when ready
            logger.info("Whisper-stream should now be ready for audio input")
            
        except Exception as e:
            logger.error(f"Failed to start whisper.cpp stream: {e}")
            raise
            
    def _is_likely_hallucination(self, text: str) -> bool:
        """Enhanced detection of whisper hallucinations and non-speech tokens"""
        text_lower = text.lower().strip()
        
        # Common whisper hallucinations
        hallucinations = [
            "[ silence ]", "[music]", "[blank_audio]", "[silence]", 
            "[music]", "[music playing]", "[applause]", "[laughter]",
            "[background music]", "[inaudible]", "[no audio]", "[noise]",
            "(audience member", "(background", "(music", "(silence",
            "thank you.", "thanks.", "bye.", "goodbye.", "okay.", "ok.",
            "mm-hmm.", "uh-huh.", "yeah.", "yes.", "no.", "right.",
            # Common single word hallucinations during silence
            "the", "and", "to", "of", "a", "in", "that", "it", "with", "for"
        ]
        
        # Exact matches
        if text_lower in hallucinations:
            return True
            
        # Pattern matching
        patterns = [
            text_lower.startswith("[") and text_lower.endswith("]"),  # Bracketed tokens
            text_lower.startswith("(") and text_lower.endswith(")"),  # Parenthetical comments
            len(text.split()) == 1 and len(text) < 4,  # Very short single words
            text_lower.count("thank") > 0 and len(text.split()) < 3,  # Short thank you variants
        ]
        
        if any(patterns):
            return True
            
        # Repetitive patterns (common in hallucinations)
        words = text.split()
        if len(words) > 2:
            # Check for word repetition
            unique_words = set(words)
            if len(unique_words) / len(words) < 0.5:  # More than 50% repetition
                return True
        
        return False


    async def _handle_config_change(self, event_data: dict):
        """Handle configuration change events for dynamic language switching"""
        try:
            component = event_data.get("component")
            settings = event_data.get("settings", {})
            
            if component == "stt" and "language" in settings:
                new_language = settings["language"]
                logger.info(f"🔄 STT language change requested: {self._language} -> {new_language}")
                
                # Validate language setting
                if new_language and new_language.lower() == "auto":
                    logger.warning("⚠️  WhisperCpp stream tool doesn't support 'auto' language detection")
                    logger.warning(f"⚠️  Ignoring auto setting - keeping current language: {self._language}")
                    return
                
                if new_language != self._language:
                    self._config_language = new_language
                    self._language = new_language
                    self._needs_restart = True
                    logger.info(f"✅ Language updated to: {new_language}")
                    
                    # Restart the whisper process with new language
                    if self._is_running:
                        logger.info("🔄 Restarting whisper-stream with new language...")
                        await self._restart_with_new_language()
                    else:
                        logger.info("⏳ Process not running, will use new language on next start")
                        
            elif component == "user_language":
                # Handle unified language updates
                new_language = str(settings) if isinstance(settings, str) else settings.get("language", settings)
                logger.info(f"🌍 User language change: {self._language} -> {new_language}")
                
                # Validate language setting
                if new_language and new_language.lower() == "auto":
                    logger.warning("⚠️  WhisperCpp stream tool doesn't support 'auto' language detection")
                    logger.warning(f"⚠️  Ignoring auto setting - keeping current language: {self._language}")
                    return
                
                if new_language != self._language:
                    self._config_language = new_language
                    self._language = new_language
                    self._needs_restart = True
                    
                    if self._is_running:
                        logger.info("🔄 Restarting whisper-stream for user language change...")
                        await self._restart_with_new_language()
                        
        except Exception as e:
            logger.error(f"❌ Error handling config change: {e}")
    
    async def _handle_tts_start(self, event_data: dict):
        """Handle TTS start events to track what text is being spoken"""
        try:
            text = event_data.get("text", "")
            if text:
                current_time = time.time()
                self._recent_tts_texts.append((text.lower().strip(), current_time))
                # Clean old entries
                self._recent_tts_texts = [
                    (t, ts) for t, ts in self._recent_tts_texts 
                    if current_time - ts <= self._tts_buffer_duration
                ]
                logger.debug(f"🔊 Tracking TTS text for feedback prevention: '{text}'")
                
                # AUDIO FEEDBACK PREVENTION: Pause whisper-stream during TTS playback
                if self._whisper_process and self._whisper_process.poll() is None:
                    logger.info("🔇 TTS started - pausing whisper-stream to prevent feedback")
                    self._pause_for_tts()
                    
        except Exception as e:
            logger.error(f"❌ Error handling TTS start event: {e}")
    
    async def _handle_tts_complete(self, event_data: dict):
        """Handle TTS completion events"""
        logger.debug("🔊 TTS playback completed")
        
        # AUDIO FEEDBACK PREVENTION: Resume whisper-stream after TTS completes
        if not self._is_running and hasattr(self, '_paused_for_tts') and self._paused_for_tts:
            logger.info("🎤 TTS completed - resuming whisper-stream")
            await asyncio.sleep(0.5)  # Brief delay to ensure audio settles
            self._resume_after_tts()
    
    def _is_tts_feedback(self, transcribed_text: str) -> bool:
        """Check if transcribed text is likely TTS feedback/echo"""
        if not self._recent_tts_texts or not transcribed_text:
            return False
        
        transcribed_lower = transcribed_text.lower().strip()
        current_time = time.time()
        
        # Clean old TTS texts
        self._recent_tts_texts = [
            (text, ts) for text, ts in self._recent_tts_texts 
            if current_time - ts <= self._tts_buffer_duration
        ]
        
        # Check similarity with recent TTS texts
        for tts_text, _ in self._recent_tts_texts:
            similarity = self._calculate_text_similarity(transcribed_lower, tts_text)
            if similarity >= self._similarity_threshold:
                logger.info(f"🔍 TTS feedback detected (similarity: {similarity:.2f}): '{transcribed_text}' ≈ '{tts_text}'")
                return True
        
        return False
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings"""
        if not text1 or not text2:
            return 0.0
        
        # Simple word-based similarity
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _handle_user_started_speaking(self):
        """Handle VAD event when user starts speaking"""
        self._user_is_speaking = True
        self._speech_session_active = True
        self._user_stopped_time = 0.0
        logger.debug("🎤 VAD: User started speaking - accepting transcriptions")
    
    def _handle_user_stopped_speaking(self):
        """Handle VAD event when user stops speaking"""
        self._user_is_speaking = False
        self._user_stopped_time = time.time()
        logger.debug("🛑 VAD: User stopped speaking - will flush pending segments and stop accepting new ones")
        
        # Immediately flush any pending segments to complete the utterance
        complete_utterance = self._boundary_detector.session_ended()
        if complete_utterance:
            logger.info(f"🚀 VAD-triggered utterance completion: '{complete_utterance}'")
            self._emit_complete_utterance(complete_utterance)
        
        # Mark speech session as ending
        self._speech_session_active = False
    
    def _should_accept_transcription(self) -> bool:
        """Check if we should accept transcriptions based on VAD state"""
        if self._user_is_speaking:
            return True
        
        # Allow transcriptions for a short grace period after user stops speaking
        if self._user_stopped_time > 0:
            time_since_stopped = time.time() - self._user_stopped_time
            return time_since_stopped <= self._vad_grace_period
        
        return False
    
    def _pause_for_tts(self):
        """Pause whisper-stream process during TTS playback to prevent feedback"""
        if self._whisper_process and self._whisper_process.poll() is None:
            try:
                logger.info("⏸️  Sending SIGTERM to pause whisper-stream (prevents feedback)")
                self._whisper_process.terminate()
                self._paused_for_tts = True
                self._is_running = False
                logger.info("✅ Whisper-stream paused for TTS playback")
            except Exception as e:
                logger.error(f"❌ Error pausing whisper-stream: {e}")
    
    def _resume_after_tts(self):
        """Resume whisper-stream process after TTS completes"""
        try:
            if self._paused_for_tts and not self._is_running:
                logger.info("🎤 Restarting whisper-stream after TTS completion")
                self._start_streaming_process()
                self._paused_for_tts = False
                logger.info("✅ Whisper-stream resumed and ready for speech")
        except Exception as e:
            logger.error(f"❌ Error resuming whisper-stream: {e}")
            
    async def _restart_with_new_language(self):
        """Restart the whisper-stream process with updated language settings"""
        try:
            logger.info(f"🛑 Stopping current whisper-stream process...")
            self._stop_streaming_process()
            
            # Give process time to fully stop
            await asyncio.sleep(0.5)
            
            logger.info(f"🚀 Starting whisper-stream with language: {self._language}")
            self._start_streaming_process()
            self._needs_restart = False
            
            logger.info("✅ Whisper-stream restarted successfully with new language")
            
        except Exception as e:
            logger.error(f"❌ Error restarting whisper-stream: {e}")
            self._needs_restart = True  # Mark for retry

    def _stop_streaming_process(self):
        """Stop the whisper.cpp streaming process"""
        if self._whisper_process:
            try:
                logger.info(f"🛑 Terminating whisper-stream process (PID: {self._whisper_process.pid})")
                self._whisper_process.terminate()
                self._whisper_process.wait(timeout=3)
                logger.info("✅ Process terminated gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("⚠️ Process didn't terminate gracefully, forcing kill")
                self._whisper_process.kill()
                self._whisper_process.wait(timeout=2)
                logger.info("✅ Process killed forcefully")
            except Exception as e:
                logger.error(f"❌ Error stopping whisper.cpp process: {e}")
                
        self._whisper_process = None
        self._is_running = False
        self._is_preloaded = False
        self._state = TranscriptionState.IDLE
        logger.info("🏁 Whisper-stream process stopped and resources cleaned up")
    
    def force_cleanup(self):
        """Force cleanup of any runaway whisper-stream processes (emergency stop)"""
        import subprocess
        
        logger.info("🚨 Force cleanup: Killing runaway processes...")
        
        # Kill our own process if it exists
        if self._whisper_process:
            try:
                if self._whisper_process.poll() is None:
                    logger.info(f"🛑 Force killing our whisper-stream process (PID: {self._whisper_process.pid})")
                    self._whisper_process.kill()
                    self._whisper_process.wait(timeout=2)
            except Exception as e:
                logger.error(f"❌ Error force killing process: {e}")
        
        # Nuclear option: pkill all whisper-stream and maestrocat processes
        try:
            logger.info("🔥 Running pkill commands for complete cleanup...")
            
            # Kill whisper-stream processes
            result1 = subprocess.run(
                ["pkill", "-9", "-f", "whisper-stream"], 
                capture_output=True, text=True, timeout=5
            )
            if result1.returncode == 0:
                logger.info("✅ pkill whisper-stream successful")
            else:
                logger.info("ℹ️  No whisper-stream processes found")
            
            # Kill maestrocat processes (be careful - this might kill us too!)
            result2 = subprocess.run(
                ["pkill", "-9", "-f", "maestrocat.*\\.py"], 
                capture_output=True, text=True, timeout=5
            )
            if result2.returncode == 0:
                logger.info("✅ pkill maestrocat*.py successful")
            else:
                logger.info("ℹ️  No maestrocat processes found")
                
        except subprocess.TimeoutExpired:
            logger.warning("⚠️  pkill commands timed out")
        except FileNotFoundError:
            logger.warning("⚠️  pkill command not found on system")
        except Exception as e:
            logger.error(f"❌ Error running pkill: {e}")
        
        # Reset our state
        self._whisper_process = None
        self._is_running = False
        self._is_preloaded = False
        self._state = TranscriptionState.IDLE
        logger.info("🧹 Force cleanup completed - processes should be dead")
        
    def _read_stdout(self):
        """Read and parse whisper.cpp stdout for transcriptions"""
        logger.info("Starting stdout reader thread - waiting for transcriptions...")
        
        # Use the approach from the GitHub example - direct line reading
        try:
            for line in self._whisper_process.stdout:
                if not self._is_running:
                    break
                    
                transcript = line.strip()
                # logger.debug(f"Raw stdout line: '{transcript}'")
                
                if transcript:
                    # logger.info(f"Processing transcription: '{transcript}'")
                    self._process_transcription_line(transcript)
                    
        except Exception as e:
            logger.error(f"Error reading stdout: {e}")
            
        logger.info("Stdout reader thread ending")
                
    def _read_stderr(self):
        """Read stderr for debugging and initialization tracking"""
        logger.info("Starting stderr reader thread")
        
        try:
            for line in self._whisper_process.stderr:
                if not self._is_running:
                    break
                    
                line = line.strip()
                if line:
                    # Track initialization progress
                    self._track_initialization_progress(line)
                    
                    if "error" in line.lower():
                        logger.error(f"Whisper.cpp stderr ERROR: {line}")
                    else:
                        logger.info(f"Whisper.cpp stderr: {line}")
                        
        except Exception as e:
            logger.error(f"Error reading stderr: {e}")
            
        logger.info("Stderr reader thread ending")
        
    def _track_initialization_progress(self, line: str):
        """Track whisper.cpp initialization progress through stderr messages"""
        line_lower = line.lower()
        
        # Track key initialization milestones
        if "whisper_model_load: model size" in line_lower:
            # Model file loading is complete
            self._model_load_complete = True
            logger.debug("🔄 Model file loading complete")
            
        elif "compute buffer (decode)" in line_lower:
            # All compute buffers allocated - this is typically the last step
            self._initialization_complete = True
            logger.debug("🔄 All compute buffers allocated - initialization nearly complete")
            
        elif "main: processing" in line_lower and "samples" in line_lower:
            # Processing loop started - definitely ready
            if self._model_load_complete:
                self._initialization_complete = True
                logger.debug("🔄 Processing loop started - fully initialized")
                
        elif "main: n_new_line" in line_lower:
            # Final initialization message - definitely ready
            if self._model_load_complete:
                self._initialization_complete = True
                logger.debug("🔄 Final initialization complete")
                
    def _process_transcription_line(self, line: str):
        """Process a transcription line from whisper.cpp using utterance boundary detection"""
        if not line.strip():
            return
            
        line = line.strip()
        
        # Check if we should accept this transcription based on VAD state
        if not self._should_accept_transcription():
            logger.debug(f"🚫 Rejecting late transcription (user stopped speaking): '{line}'")
            return
        
        # Handle transcription session markers
        if line.startswith("###"):
            self._handle_session_marker(line)
            return
            
        # Skip debug/status messages, control characters, and whisper hallucinations
        if (line.startswith("[Start speaking]") or 
            line.startswith("\x1b") or  # ANSI escape sequences
            line.startswith("\x08") or  # Backspace
            line.startswith("\r") or    # Carriage return
            line == "\x1b[2K\r" or     # Clear line escape
            "[2K" in line or           # ANSI clear line sequence (any variation)
            line.strip() == "[2K" or   # Just the clear sequence
            line.strip().startswith("\x1b[") or  # Any ANSI escape sequence
            self._is_likely_hallucination(line) or  # Enhanced hallucination detection
            not any(c.isalnum() for c in line)):
            logger.debug(f"Skipping debug/control/hallucination line: {line!r}")
            return
            
        # Parse timestamp and text from whisper-stream format: [start_time --> end_time] text
        segment = self._parse_timestamped_segment(line)
        if segment is None:
            logger.debug(f"Failed to parse segment, line format: {line!r}")
            # If it's not a timestamped segment, treat as direct transcription
            if not any(skip in line for skip in ['[BLANK_AUDIO]', '[ Silence ]', '[Start speaking]']):
                # Check for duplicate transcription to prevent duplicates
                if line != self._current_transcription:
                    logger.info(f"Direct transcription (no timestamp): '{line}'")
                    self._emit_complete_utterance(line)
                else:
                    logger.debug(f"Skipping duplicate transcription: '{line}'")
            return
            
        # Use boundary detector to determine if utterance is complete
        complete_utterance = self._boundary_detector.add_segment(segment, getattr(self, '_current_session_id', None))
        
        if complete_utterance:
            logger.info(f"Complete utterance detected: '{complete_utterance}'")
            self._emit_complete_utterance(complete_utterance)
        else:
            logger.debug(f"Segment added to buffer: '{segment.text}'")
            
        # Check for timeout-based utterance completion
        timeout_utterance = self._boundary_detector.check_timeout()
        if timeout_utterance:
            logger.info(f"Timeout-based utterance completion: '{timeout_utterance}'")
            self._emit_complete_utterance(timeout_utterance)
            
    def _handle_session_marker(self, line: str):
        """Handle whisper-stream session start/end markers"""
        if "START" in line:
            # Extract session ID from line like: ### Transcription 5 START | t0 = ...
            parts = line.split()
            if len(parts) >= 3:
                try:
                    session_id = f"session_{parts[2]}"
                    self._current_session_id = session_id
                    logger.debug(f"Started transcription session: {session_id}")
                except (IndexError, ValueError):
                    self._current_session_id = f"session_{int(time.time())}"
        elif "END" in line:
            # Session ended - finalize any pending utterance
            if hasattr(self, '_current_session_id'):
                complete_utterance = self._boundary_detector.session_ended(self._current_session_id)
                if complete_utterance:
                    logger.info(f"Session-ended utterance: '{complete_utterance}'")
                    self._emit_complete_utterance(complete_utterance)
                self._current_session_id = None
                
    def _parse_timestamped_segment(self, line: str) -> Optional[TranscriptionSegment]:
        """Parse a timestamped segment from whisper-stream output"""
        if not line.startswith("[") or "]" not in line:
            return None
            
        # Skip ANSI escape sequences that might look like timestamps
        if "[2K" in line or line.strip().startswith("[2K"):
            return None
            
        # Extract timestamp and text: [00:00:01.000 --> 00:00:03.000] text
        bracket_end = line.find("]")
        if bracket_end == -1:
            return None
            
        timestamp_part = line[1:bracket_end]  # Remove brackets
        text_part = line[bracket_end + 1:].strip()
        
        # Validate timestamp format - must contain time indicators
        if not any(char in timestamp_part for char in [':',  '-->']):
            logger.debug(f"Invalid timestamp format, skipping: {line!r}")
            return None
        
        if not text_part or self._is_likely_hallucination(text_part):
            return None
            
        # Parse timestamps
        try:
            if " --> " in timestamp_part:
                start_str, end_str = timestamp_part.split(" --> ")
                start_time = self._parse_timestamp(start_str.strip())
                end_time = self._parse_timestamp(end_str.strip())
            else:
                # Fallback for malformed timestamps
                start_time = 0.0
                end_time = 1.0
                
            return TranscriptionSegment(
                text=text_part,
                start_time=start_time,
                end_time=end_time,
                confidence=0.9,
                timestamp=time.time()
            )
        except Exception as e:
            logger.debug(f"Failed to parse timestamps from '{timestamp_part}': {e}")
            return None
            
    def _parse_timestamp(self, timestamp_str: str) -> float:
        """Parse timestamp string like '00:00:01.500' to seconds"""
        try:
            parts = timestamp_str.split(":")
            if len(parts) == 3:
                hours = float(parts[0])
                minutes = float(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 2:
                minutes = float(parts[0])
                seconds = float(parts[1])
                return minutes * 60 + seconds
            else:
                return float(parts[0])
        except (ValueError, IndexError):
            return 0.0
            
    def _emit_complete_utterance(self, utterance_text: str):
        """Emit a complete utterance to the pipeline"""
        current_time = time.time()
        
        # Check for audio feedback (TTS echo)
        if self._is_tts_feedback(utterance_text):
            logger.warning(f"🔇 BLOCKING TTS FEEDBACK: '{utterance_text}'")
            return
        
        # Check for duplicate emission (within time window)
        if (utterance_text == self._last_emitted_text and 
            current_time - self._last_emission_time < self._dedup_time_window):
            logger.debug(f"🔇 BLOCKING DUPLICATE EMISSION: '{utterance_text}'")
            return
        
        # Track this emission for deduplication
        self._last_emitted_text = utterance_text
        self._last_emission_time = current_time
        
        logger.info(f"🚀 EMITTING UTTERANCE TO LLM: '{utterance_text}'")
        self._last_activity_time = current_time
        
        # Create final transcription
        transcription = StreamingTranscription(
            text=utterance_text,
            is_partial=False,
            confidence=0.9,
            timestamp=current_time,
            duration=0.0
        )
        
        # Emit to pipeline
        if hasattr(self, '_loop') and self._loop:
            logger.info(f"📤 Sending to event loop: '{utterance_text}'")
            asyncio.run_coroutine_threadsafe(self._emit_transcription(transcription), self._loop)
        else:
            logger.warning("❌ No event loop available to emit transcription")
            
        # Update state
        self._current_transcription = utterance_text
        
    async def _timeout_checker_loop(self):
        """Periodically check for timeout-based utterance completion and idle process management"""
        logger.debug("Starting timeout checker loop")
        
        try:
            while self._is_running:
                await asyncio.sleep(self._timeout_check_interval)
                current_time = time.time()
                
                # Check for timeout-based utterance completion
                timeout_utterance = self._boundary_detector.check_timeout()
                if timeout_utterance:
                    logger.info(f"Timeout-based utterance completion: '{timeout_utterance}'")
                    self._emit_complete_utterance(timeout_utterance)
                
                # More aggressive completion when user has stopped speaking
                if (not self._user_is_speaking and self._user_stopped_time > 0 and 
                    current_time - self._user_stopped_time > 0.5):  # 500ms after stop
                    vad_completion = self._boundary_detector.session_ended()
                    if vad_completion:
                        logger.info(f"VAD-based completion after 500ms: '{vad_completion}'")
                        self._emit_complete_utterance(vad_completion)
                
                # Check for idle timeout to save resources
                if (self._last_activity_time > 0 and 
                    current_time - self._last_activity_time > self._idle_timeout and
                    self._whisper_process and self._whisper_process.poll() is None):
                    logger.info(f"⏰ No activity for {self._idle_timeout}s, stopping whisper-stream to save resources")
                    self._stop_streaming_process()
                    
        except asyncio.CancelledError:
            logger.debug("Timeout checker loop cancelled")
        except Exception as e:
            logger.error(f"Error in timeout checker loop: {e}")
            
    async def _emit_transcription(self, transcription: StreamingTranscription):
        """Emit transcription to the pipeline"""
        try:
            logger.info(f"🔄 Creating TranscriptionFrame: '{transcription.text}'")
            
            # Create transcription frame
            frame = TranscriptionFrame(
                text=transcription.text,
                user_id="user",
                timestamp=transcription.timestamp
            )
            
            logger.info(f"📨 Pushing frame to pipeline: '{transcription.text}'")
            # Push to pipeline
            await self.push_frame(frame)
            logger.info(f"✅ Frame pushed successfully: '{transcription.text}'")
            
            # Emit debug events
            if self._event_emitter:
                event_type = "transcription_partial" if transcription.is_partial else "transcription_final"
                await self._event_emitter.emit(event_type, {
                    "text": transcription.text,
                    "is_partial": transcription.is_partial,
                    "timestamp": transcription.timestamp,
                    "confidence": transcription.confidence
                })
                
        except Exception as e:
            logger.error(f"Error emitting transcription: {e}")
            
    async def start(self, frame: Frame):
        """Start the streaming service"""
        await super().start(frame)
        # Capture the current event loop for thread-safe async calls
        self._loop = asyncio.get_event_loop()
        
        # Pre-load model if not already done for fast first response
        if not self._is_preloaded:
            logger.info("🚀 Pre-loading whisper-stream for instant first transcription...")
            await self._preload_model()
        else:
            logger.info("🎤 STT service ready - whisper-stream already pre-loaded")
            
        self._last_activity_time = time.time()
        
        # Start timeout checker task
        self._timeout_checker_task = asyncio.create_task(self._timeout_checker_loop())
        
    async def stop(self, frame: Frame):
        """Stop the streaming service"""
        self._stop_streaming_process()
        
        # Stop timeout checker task
        if self._timeout_checker_task:
            self._timeout_checker_task.cancel()
            try:
                await self._timeout_checker_task
            except asyncio.CancelledError:
                pass
        
        await super().stop(frame)
    
    async def cleanup(self):
        """Clean up resources when service is being destroyed"""
        logger.info("🧹 Cleaning up WhisperCppStreamingSTTService...")
        
        # Set running flag to false
        self._is_running = False
        
        # Stop the whisper process
        self._stop_streaming_process()
        
        # Cancel timeout checker task
        if self._timeout_checker_task:
            self._timeout_checker_task.cancel()
            try:
                await self._timeout_checker_task
            except asyncio.CancelledError:
                pass
        
        # Join reader threads
        if hasattr(self, '_stdout_reader_thread') and self._stdout_reader_thread:
            self._stdout_reader_thread.join(timeout=1.0)
        if hasattr(self, '_stderr_reader_thread') and self._stderr_reader_thread:
            self._stderr_reader_thread.join(timeout=1.0)
        
        # Force cleanup if process still exists
        if self._whisper_process:
            try:
                self._whisper_process.kill()
                self._whisper_process.wait(timeout=1.0)
            except:
                pass
            self._whisper_process = None
        
        logger.info("✅ WhisperCppStreamingSTTService cleanup complete")
        
    def write_audio(self, audio: bytes):
        """Note: whisper-stream captures audio directly via SDL2, so this is a no-op"""
        # whisper-stream binary captures audio directly from the microphone using SDL2
        # We don't need to (and can't) pipe audio data to it
        _ = audio  # Silence unused parameter warning
        pass
            
    async def process_frame(self, frame: Frame, direction):
        """Process incoming audio frames"""
        await super().process_frame(frame, direction)
        
        # Handle VAD events
        if isinstance(frame, UserStartedSpeakingFrame):
            self._handle_user_started_speaking()
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._handle_user_stopped_speaking()
        
        # Start whisper-stream on-demand when audio is detected
        from pipecat.frames.frames import AudioRawFrame
        if isinstance(frame, AudioRawFrame) and not self._is_running:
            logger.info("🎤 Audio detected - starting whisper-stream on-demand")
            self._start_streaming_process()
            self._last_activity_time = time.time()
        
        # Update activity time for any audio frame
        if isinstance(frame, AudioRawFrame):
            self._last_activity_time = time.time()
        
        # Note: whisper-stream captures audio directly via SDL2
        # We just pass frames through the pipeline for VAD and interruption handling
        
        # Pass frame downstream
        await self.push_frame(frame, direction)
        
    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Required by STTService but not used in streaming mode"""
        _ = audio  # Silence unused parameter warning
        yield  # Make this an async generator