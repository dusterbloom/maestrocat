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

from pipecat.frames.frames import Frame, TranscriptionFrame, StartInterruptionFrame
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
        """Merge segments into a single utterance, handling overlaps"""
        if not segments:
            return ""
            
        if len(segments) == 1:
            return segments[0].text
            
        # Merge segments with overlap detection
        merged_parts = []
        
        for i, segment in enumerate(segments):
            text = segment.text.strip()
            if not text:
                continue
                
            if i == 0:
                merged_parts.append(text)
            else:
                # Check for overlap with previous segments
                prev_text = " ".join(merged_parts)
                
                # Simple overlap detection - if current segment starts with end of previous
                words_current = text.split()
                words_prev = prev_text.split()
                
                # Find overlap
                max_overlap = min(len(words_current), len(words_prev), 3)  # Check up to 3 words
                overlap_found = False
                
                for overlap_len in range(max_overlap, 0, -1):
                    if words_prev[-overlap_len:] == words_current[:overlap_len]:
                        # Overlap found - merge without duplication
                        remaining_words = words_current[overlap_len:]
                        if remaining_words:
                            merged_parts.extend(remaining_words)
                        overlap_found = True
                        break
                        
                if not overlap_found:
                    # No overlap - just append
                    merged_parts.extend(words_current)
                    
        return " ".join(merged_parts)


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
        language: str = "auto",
        translate: bool = False,
        sample_rate: int = 16000,
        channels: int = 1,
        block_size: int = 512,
        max_latency_ms: int = 200,
        step_ms: int = 1000,
        length_ms: int = 5000,
        keep_ms: int = 200,
        voice_threshold: float = 0.8,
        threads: int = 6,
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
        
        # Utterance boundary detection
        self._boundary_detector = UtteranceBoundaryDetector(
            silence_threshold_ms=600.0,  # 600ms gap indicates utterance boundary
            completion_timeout_ms=2500.0,  # 2.5s timeout for incomplete utterances
            min_utterance_length=3  # Minimum 3 characters for valid utterance
        )
        
        # Legacy sliding window overlap handling (fallback for edge cases)
        # NOTE: With fixed step mode (--step 1000), this should no longer be needed
        self._transcription_buffer = []  # Store recent transcriptions for overlap detection
        self._buffer_max_size = 5  # Keep last 5 transcriptions for overlap analysis
        self._overlap_threshold = 0.7  # Similarity threshold for overlap detection
        
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
        
        # Language change handling
        self._original_language = language  # Store original for comparison
        self._config_language = language  # Track config language separately
        self._needs_restart = False  # Flag to track if restart is needed
        
        # Find whisper.cpp stream binary
        self._stream_binary = self._find_stream_binary()
        if not self._stream_binary:
            raise RuntimeError(
                "whisper.cpp stream binary not found. "
                "Please run: ./build_whispercpp_stream.sh"
            )
        
        # Ensure model exists
        self._ensure_model()
        
        # Subscribe to config change events if event emitter is available
        if self._event_emitter:
            self._event_emitter.subscribe("config_change", self._handle_config_change)
            logger.info("🔔 Subscribed to config_change events for dynamic language updates")
        
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
        """Ensure the Whisper model is available"""
        if self._model_path and os.path.exists(self._model_path):
            return
            
        # Search for model in common locations
        model_file = f"ggml-{self._model_size}.bin"
        search_dirs = [
            "./mlx_models",
            "./models", 
            "./whisper.cpp/models",
            os.path.expanduser("~/.cache/whisper"),
            os.path.expanduser("~/models"),
        ]
        
        for models_dir in search_dirs:
            if os.path.exists(models_dir):
                model_path = os.path.join(models_dir, model_file)
                if os.path.exists(model_path):
                    self._model_path = model_path
                    logger.info(f"Found model at: {self._model_path}")
                    return
        
        # Fallback to default cache directory
        default_dir = os.path.expanduser("~/.cache/whisper")
        os.makedirs(default_dir, exist_ok=True)
        self._model_path = os.path.join(default_dir, model_file)
        
        logger.warning(
            f"Model file not found. Searched in: {search_dirs}. "
            f"Using fallback path: {self._model_path}. "
            f"Please download the model manually or use whisper.cpp's download script."
        )
            
    def _start_streaming_process(self):
        """Start the whisper.cpp streaming process"""
        if self._whisper_process and self._whisper_process.poll() is None:
            return
            
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
        
        # Handle language setting - only add -l flag if not auto-detecting
        if self._language and self._language.lower() != "auto":
            cmd.extend(["-l", self._language])
            logger.info(f"🌍 Using explicit language: {self._language}")
        else:
            logger.info("🤖 Using automatic language detection - whisper will detect and transcribe in detected language")
        
        # Add keep-context flag for better language consistency (based on whisper-stream help)
        if not self._translate and self._language and self._language.lower() not in ["en", "auto"]:
            cmd.append("-kc")  # Keep context between chunks for consistency
            logger.info("🔗 Added --keep-context flag for language consistency")
        elif self._language and self._language.lower() == "auto":
            cmd.append("-kc")  # Always use keep-context for auto-detection to maintain consistency
            logger.info("🔗 Added --keep-context flag for auto-detection consistency")
        
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
            
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings using word overlap"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
            
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _find_text_overlap(self, text1: str, text2: str) -> str:
        """Find overlapping portion between two texts and return merged result"""
        words1 = text1.split()
        words2 = text2.split()
        
        # Look for suffix of text1 that matches prefix of text2
        max_overlap = 0
        best_merge = text2  # Default to just using text2
        
        for i in range(1, min(len(words1), len(words2)) + 1):
            suffix = words1[-i:]
            prefix = words2[:i]
            
            if suffix == prefix:
                max_overlap = i
                # Merge: text1 + remaining part of text2
                best_merge = text1 + " " + " ".join(words2[i:])
        
        # If significant overlap found, use merged version
        if max_overlap > 0:
            logger.debug(f"Found overlap of {max_overlap} words, merged: '{text1}' + '{text2}' -> '{best_merge}'")
            return best_merge
        
        return text2  # No overlap, return new text
    
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

    def _handle_sliding_window_overlap(self, text: str) -> str:
        """Handle overlapping transcriptions from sliding window chunks"""
        if not hasattr(self, '_transcription_buffer'):
            self._transcription_buffer = []
        
        # Clean old entries (keep last N transcriptions)
        if len(self._transcription_buffer) > self._buffer_max_size:
            self._transcription_buffer = self._transcription_buffer[-self._buffer_max_size:]
        
        # Check for exact duplicates
        for prev_text, _ in self._transcription_buffer:
            if text == prev_text:
                logger.debug(f"Exact duplicate found, skipping: '{text}'")
                return None
        
        # Check for high similarity (likely overlapping chunks)
        for prev_text, timestamp in self._transcription_buffer:
            similarity = self._calculate_text_similarity(text, prev_text)
            
            if similarity > self._overlap_threshold:
                # High similarity detected - try to merge
                merged_text = self._find_text_overlap(prev_text, text)
                
                # If merged text is significantly different from both inputs, use it
                if (merged_text != text and merged_text != prev_text and 
                    len(merged_text.split()) > max(len(text.split()), len(prev_text.split()))):
                    logger.info(f"Merged overlapping transcriptions: '{merged_text}'")
                    # Update buffer with merged result
                    self._transcription_buffer = [(t, ts) for t, ts in self._transcription_buffer if t != prev_text]
                    self._transcription_buffer.append((merged_text, time.time()))
                    return merged_text
                else:
                    # Similar but can't merge well - skip this transcription
                    logger.debug(f"High similarity ({similarity:.2f}) detected, skipping: '{text}'")
                    return None
        
        # No significant overlap found - add to buffer and process
        self._transcription_buffer.append((text, time.time()))
        return text

    async def _handle_config_change(self, event_data: dict):
        """Handle configuration change events for dynamic language switching"""
        try:
            component = event_data.get("component")
            settings = event_data.get("settings", {})
            
            if component == "stt" and "language" in settings:
                new_language = settings["language"]
                logger.info(f"🔄 STT language change requested: {self._language} -> {new_language}")
                
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
                
                if new_language != self._language:
                    self._config_language = new_language
                    self._language = new_language
                    self._needs_restart = True
                    
                    if self._is_running:
                        logger.info("🔄 Restarting whisper-stream for user language change...")
                        await self._restart_with_new_language()
                        
        except Exception as e:
            logger.error(f"❌ Error handling config change: {e}")
            
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
                self._whisper_process.terminate()
                self._whisper_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._whisper_process.kill()
            except Exception as e:
                logger.error(f"Error stopping whisper.cpp process: {e}")
                
        self._is_running = False
        self._state = TranscriptionState.IDLE
        
    def _read_stdout(self):
        """Read and parse whisper.cpp stdout for transcriptions"""
        logger.info("Starting stdout reader thread - waiting for transcriptions...")
        
        # Use the approach from the GitHub example - direct line reading
        try:
            for line in self._whisper_process.stdout:
                if not self._is_running:
                    break
                    
                transcript = line.strip()
                logger.debug(f"Raw stdout line: '{transcript}'")
                
                if transcript:
                    logger.info(f"Processing transcription: '{transcript}'")
                    self._process_transcription_line(transcript)
                    
        except Exception as e:
            logger.error(f"Error reading stdout: {e}")
            
        logger.info("Stdout reader thread ending")
                
    def _read_stderr(self):
        """Read stderr for debugging"""
        logger.info("Starting stderr reader thread")
        
        try:
            for line in self._whisper_process.stderr:
                if not self._is_running:
                    break
                    
                line = line.strip()
                if line:
                    if "error" in line.lower():
                        logger.error(f"Whisper.cpp stderr ERROR: {line}")
                    else:
                        logger.info(f"Whisper.cpp stderr: {line}")
                        
        except Exception as e:
            logger.error(f"Error reading stderr: {e}")
            
        logger.info("Stderr reader thread ending")
                
    def _process_transcription_line(self, line: str):
        """Process a transcription line from whisper.cpp using utterance boundary detection"""
        if not line.strip():
            return
            
        line = line.strip()
        
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
                logger.info(f"Direct transcription (no timestamp): '{line}'")
                self._emit_complete_utterance(line)
            return
            
        # Use boundary detector to determine if utterance is complete
        complete_utterance = self._boundary_detector.add_segment(segment, getattr(self, '_current_session_id', None))
        
        if complete_utterance:
            logger.info(f"Complete utterance detected: '{complete_utterance}'")
            self._emit_complete_utterance(complete_utterance)
        else:
            logger.debug(f"Segment added to buffer: '{segment.text}'")
            
        # Simple timeout-based completion - just check basic timeout
        timeout_utterance = self._boundary_detector.check_timeout()
        logger.debug(f"Timeout check result: '{timeout_utterance}' (length: {len(timeout_utterance) if timeout_utterance else 0})")
        if timeout_utterance and len(timeout_utterance.strip()) > 2:
            logger.info(f"Timeout-based utterance completion: '{timeout_utterance}'")
            self._emit_complete_utterance(timeout_utterance)
        else:
            logger.debug(f"No timeout emission - utterance too short or None")
            
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
        
        logger.info(f"🚀 EMITTING UTTERANCE TO LLM: '{utterance_text}'")
        
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
        """Periodically check for timeout-based utterance completion"""
        logger.debug("Starting timeout checker loop")
        
        try:
            while self._is_running:
                await asyncio.sleep(self._timeout_check_interval)
                
                # Check for timeout-based completion
                timeout_utterance = self._boundary_detector.check_timeout()
                if timeout_utterance:
                    logger.info(f"Timeout-based utterance completion: '{timeout_utterance}'")
                    self._emit_complete_utterance(timeout_utterance)
                    
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
        self._start_streaming_process()
        
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
        
    def write_audio(self, audio: bytes):
        """Note: whisper-stream captures audio directly via SDL2, so this is a no-op"""
        # whisper-stream binary captures audio directly from the microphone using SDL2
        # We don't need to (and can't) pipe audio data to it
        _ = audio  # Silence unused parameter warning
        pass
            
    async def process_frame(self, frame: Frame, direction):
        """Process incoming audio frames"""
        await super().process_frame(frame, direction)
        
        # Note: whisper-stream captures audio directly via SDL2
        # We just pass frames through the pipeline for VAD and interruption handling
        
        # Pass frame downstream
        await self.push_frame(frame, direction)
        
    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Required by STTService but not used in streaming mode"""
        _ = audio  # Silence unused parameter warning
        yield  # Make this an async generator