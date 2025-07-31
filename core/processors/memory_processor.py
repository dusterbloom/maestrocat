"""
Memory Processor for MaestroCat Pipeline

Captures conversation data and optionally injects relevant context
into the LLM conversation flow.
"""

import logging
import time
import uuid
from typing import Optional, List, Dict, Any

from pipecat.frames.frames import (
    Frame, 
    TranscriptionFrame, 
    TextFrame, 
    LLMMessagesFrame,
    SystemFrame,
    StartFrame,
    EndFrame,
    InputAudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    StopInterruptionFrame
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

from ..storage.sqlite_manager import SQLiteMemoryManager

logger = logging.getLogger(__name__)


class MemoryProcessor(FrameProcessor):
    """
    Pipeline processor that captures conversation data and injects relevant context.
    
    This processor:
    1. Captures transcription frames (user input) and stores them
    2. Captures LLM responses and stores them
    3. Optionally injects relevant historical context before LLM processing
    4. Maintains session tracking for conversation continuity
    """
    
    def __init__(self,
                 *,
                 sqlite_manager: Optional[SQLiteMemoryManager] = None,
                 db_path: str = "data/memory/conversations.db",
                 context_injection_enabled: bool = True,
                 max_context_messages: int = 5,
                 context_time_window_minutes: int = 5,
                 session_id: Optional[str] = None,
                 **kwargs):
        """
        Initialize the memory processor.
        
        Args:
            sqlite_manager: Pre-configured SQLite manager (optional)
            db_path: Path to SQLite database
            context_injection_enabled: Whether to inject historical context
            max_context_messages: Maximum number of context messages to inject
            context_time_window_minutes: Time window for recent context
            session_id: Session identifier (auto-generated if not provided)
        """
        super().__init__(**kwargs)
        
        # Initialize SQLite manager
        self.sqlite_manager = sqlite_manager or SQLiteMemoryManager(db_path)
        
        # Configuration
        self.context_injection_enabled = context_injection_enabled
        self.max_context_messages = max_context_messages
        self.context_time_window_minutes = context_time_window_minutes
        
        # Session management
        self.session_id = session_id or self._generate_session_id()
        self.current_speaker_id = None
        self.current_language = None
        
        # Track LLM response state
        self._collecting_llm_response = False
        self._llm_response_buffer = []
        
        logger.info(f"✅ Memory processor initialized with session: {self.session_id}")
        
    def _generate_session_id(self) -> str:
        """Generate a unique session ID"""
        return f"session_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    async def set_context(self, context: OpenAILLMContext):
        """Set the LLM context for injection"""
        self.context = context
        
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames to capture conversation data"""
        
        # Always call parent's process_frame first to handle StartFrame properly
        await super().process_frame(frame, direction)
        
        # Skip audio and control frames - we don't process them
        if isinstance(frame, (InputAudioRawFrame, UserStartedSpeakingFrame, 
                            UserStoppedSpeakingFrame, StopInterruptionFrame)):
            return
        
        # Handle StartFrame to initialize processor
        if isinstance(frame, StartFrame):
            logger.debug("Memory processor received StartFrame")
        
        # Handle EndFrame for cleanup
        elif isinstance(frame, EndFrame):
            # Flush any remaining LLM response
            if self._collecting_llm_response and self._llm_response_buffer:
                complete_response = "".join(self._llm_response_buffer)
                await self._handle_llm_response(complete_response)
                self._llm_response_buffer = []
                self._collecting_llm_response = False
            logger.debug("Memory processor received EndFrame")
        
        # Capture user transcriptions
        elif isinstance(frame, TranscriptionFrame):
            logger.debug(f"Memory processor received TranscriptionFrame: {frame.text[:50]}...")
            await self._handle_transcription(frame)
            
            # Inject context before passing to LLM
            if self.context_injection_enabled and hasattr(self, 'context'):
                logger.debug("Injecting context into LLM conversation")
                await self._inject_context(frame.text)
        
        # Capture LLM responses
        elif isinstance(frame, TextFrame) and direction == FrameDirection.DOWNSTREAM:
            # Collect LLM response chunks
            self._llm_response_buffer.append(frame.text)
            self._collecting_llm_response = True
        
        # Detect end of LLM response
        elif isinstance(frame, SystemFrame) and self._collecting_llm_response:
            # Store complete LLM response
            if self._llm_response_buffer:
                complete_response = "".join(self._llm_response_buffer)
                await self._handle_llm_response(complete_response)
                self._llm_response_buffer = []
                self._collecting_llm_response = False
    
    async def _handle_transcription(self, frame: TranscriptionFrame):
        """Handle user transcription frames"""
        try:
            # Extract metadata from frame
            metadata = {
                "user_id": frame.user_id if hasattr(frame, 'user_id') else None,
                "timestamp": frame.timestamp if hasattr(frame, 'timestamp') else time.time()
            }
            
            # Store in database
            await self.sqlite_manager.store_message(
                session_id=self.session_id,
                role="user",
                content=frame.text,
                metadata=metadata,
                speaker_id=self.current_speaker_id,
                language=self.current_language
            )
            
            logger.debug(f"📝 Stored user message: {frame.text[:50]}...")
            
        except Exception as e:
            logger.error(f"❌ Error storing transcription: {e}")
    
    async def _handle_llm_response(self, response_text: str):
        """Handle complete LLM response"""
        try:
            metadata = {
                "timestamp": time.time(),
                "model": "llama3.2"  # Could be extracted from config
            }
            
            # Store in database
            await self.sqlite_manager.store_message(
                session_id=self.session_id,
                role="assistant",
                content=response_text,
                metadata=metadata
            )
            
            logger.debug(f"🤖 Stored assistant response: {response_text[:50]}...")
            
        except Exception as e:
            logger.error(f"❌ Error storing LLM response: {e}")
    
    async def _inject_context(self, user_input: str):
        """Inject relevant historical context into the conversation"""
        try:
            # Get recent context from current session
            recent_messages = await self.sqlite_manager.get_recent_context(
                session_id=self.session_id,
                time_window_minutes=self.context_time_window_minutes,
                max_messages=self.max_context_messages
            )
            
            if recent_messages and len(recent_messages) > 1:  # More than just current message
                # Format context for injection
                context_parts = []
                for msg in recent_messages[:-1]:  # Exclude current message
                    role = msg["role"].capitalize()
                    content = msg["content"]
                    context_parts.append(f"{role}: {content}")
                
                context_text = "\n".join(context_parts)
                
                # Create context message
                context_message = {
                    "role": "system",
                    "content": f"Recent conversation context:\n{context_text}\n\nContinue the conversation naturally based on this context."
                }
                
                # Insert context before the current user message
                # Find the last user message index
                user_msg_index = -1
                for i in range(len(self.context.messages) - 1, -1, -1):
                    if self.context.messages[i]["role"] == "user":
                        user_msg_index = i
                        break
                
                if user_msg_index > 0:
                    # Insert context before the user message
                    self.context.messages.insert(user_msg_index, context_message)
                    logger.debug(f"💉 Injected {len(recent_messages)-1} context messages")
            
            # Also search for similar past conversations (optional)
            if user_input and len(user_input) > 10:  # Only search for substantial input
                similar_convos = await self.sqlite_manager.search_conversations(
                    query=user_input,
                    limit=3
                )
                
                if similar_convos:
                    # Could inject these as additional context
                    logger.debug(f"🔍 Found {len(similar_convos)} similar past conversations")
                    
        except Exception as e:
            logger.error(f"❌ Error injecting context: {e}")
    
    async def update_speaker(self, speaker_id: str):
        """Update current speaker information"""
        self.current_speaker_id = speaker_id
        logger.debug(f"👤 Updated speaker: {speaker_id}")
    
    async def update_language(self, language: str):
        """Update current language"""
        self.current_language = language
        logger.debug(f"🌍 Updated language: {language}")
    
    async def end_session(self):
        """End the current session"""
        await self.sqlite_manager.end_session(self.session_id)
        logger.info(f"🏁 Ended session: {self.session_id}")
        
        # Generate new session ID for next conversation
        self.session_id = self._generate_session_id()
        logger.info(f"🆕 New session created: {self.session_id}")
    
    async def get_session_summary(self) -> Dict[str, Any]:
        """Get a summary of the current session"""
        history = await self.sqlite_manager.get_conversation_history(
            self.session_id,
            limit=100
        )
        
        session_info = await self.sqlite_manager.get_session_info(self.session_id)
        
        return {
            "session_id": self.session_id,
            "message_count": len(history),
            "duration_seconds": time.time() - (session_info["start_time"] if session_info else time.time()),
            "recent_messages": history[-10:] if history else []
        }
    
    async def cleanup(self):
        """Clean up resources"""
        await self.sqlite_manager.close()
        logger.info("🧹 Memory processor cleaned up")