# maestrocat/modules/memory.py
"""Memory module for conversation history and context with SQLite storage"""
from typing import Dict, Any, List, Optional
import logging
import time
import uuid

from core.modules.base import MaestroCatModule
from core.storage.sqlite_manager import SQLiteMemoryManager

logger = logging.getLogger(__name__)


class MemoryModule(MaestroCatModule):
    """
    Enhanced memory module with SQLite storage for persistent conversation history
    and context enrichment.
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        
        # Configuration
        self.db_path = config.get("database_path", "data/memory/conversations.db")
        self.max_history = config.get("max_history", 100)
        self.enable_search = config.get("enable_search", True)
        self.context_window_minutes = config.get("context_window_minutes", 30)
        
        # SQLite manager
        self.sqlite_manager = SQLiteMemoryManager(self.db_path)
        
        # Session management
        self.current_session_id = self._generate_session_id()
        self.current_speaker_id = None
        self.current_language = None
        
        # In-memory caches for performance
        self.user_facts = {}
        self.recent_topics = []
        
        logger.info(f"✅ Memory module initialized with SQLite storage at: {self.db_path}")
            
    async def initialize(self):
        """Initialize the memory module"""
        # Database is initialized in SQLiteMemoryManager constructor
        logger.info(f"🚀 Memory module ready with session: {self.current_session_id}")
    
    async def on_event(self, event_type: str, data: Any):
        """Process events to build persistent memory"""
        try:
            if event_type == "transcription_complete":
                # Store user utterance
                await self.sqlite_manager.store_message(
                    session_id=self.current_session_id,
                    role="user",
                    content=data.get("text", ""),
                    metadata={
                        "confidence": data.get("confidence"),
                        "timestamp": data.get("timestamp", time.time())
                    },
                    speaker_id=data.get("speaker_id") or self.current_speaker_id,
                    language=data.get("language") or self.current_language
                )
                
                # Extract facts asynchronously
                await self._extract_facts(data.get("text", ""))
                
                logger.debug(f"📝 Stored user message: {data.get('text', '')[:50]}...")
                
            elif event_type == "llm_response_complete":
                # Store assistant response
                await self.sqlite_manager.store_message(
                    session_id=self.current_session_id,
                    role="assistant",
                    content=data.get("text", ""),
                    metadata={
                        "model": data.get("model", "llama3.2"),
                        "timestamp": data.get("timestamp", time.time())
                    }
                )
                
                logger.debug(f"🤖 Stored assistant response: {data.get('text', '')[:50]}...")
            
            elif event_type == "speaker_identified":
                # Update current speaker
                self.current_speaker_id = data.get("speaker_id")
                logger.info(f"👤 Speaker identified: {self.current_speaker_id}")
            
            elif event_type == "language_changed":
                # Update current language
                self.current_language = data.get("language")
                logger.info(f"🌍 Language changed: {self.current_language}")
            
            elif event_type == "session_ended":
                # End current session and start new one
                await self.sqlite_manager.end_session(self.current_session_id)
                self.current_session_id = self._generate_session_id()
                logger.info(f"🔄 New session started: {self.current_session_id}")
                
        except Exception as e:
            logger.error(f"❌ Error processing event {event_type}: {e}")
            
    def _generate_session_id(self) -> str:
        """Generate a unique session ID"""
        return f"session_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    async def _extract_facts(self, text: str):
        """Extract facts from user utterances for quick access"""
        if not text:
            return
            
        text_lower = text.lower()
        
        # Extract name
        if "my name is" in text_lower:
            words = text.split("my name is")[-1].strip().split()
            if words:
                name = words[0].strip(".,!?")
                self.user_facts["name"] = name
                logger.info(f"📌 Extracted user name: {name}")
        
        # Extract preferences
        if "i like" in text_lower:
            like = text.split("i like")[-1].strip().split(".")[0].strip()
            if like:
                if "likes" not in self.user_facts:
                    self.user_facts["likes"] = []
                if like not in self.user_facts["likes"]:
                    self.user_facts["likes"].append(like)
                    logger.info(f"📌 Extracted preference: {like}")
        
        # Extract topics for context
        # Simple keyword extraction - could be enhanced with NLP
        words = text.lower().split()
        topic_keywords = [w for w in words if len(w) > 5 and w.isalpha()]
        if topic_keywords:
            self.recent_topics.extend(topic_keywords)
            self.recent_topics = self.recent_topics[-20:]  # Keep last 20 topics
            
    async def get_context(self, num_turns: int = 5) -> Dict[str, Any]:
        """Get relevant context for LLM from SQLite"""
        # Get recent conversation history
        recent_history = await self.sqlite_manager.get_recent_context(
            session_id=self.current_session_id,
            time_window_minutes=self.context_window_minutes,
            max_messages=num_turns * 2  # User + assistant messages
        )
        
        # Get session info
        session_info = await self.sqlite_manager.get_session_info(self.current_session_id)
        
        return {
            "recent_history": recent_history,
            "user_facts": self.user_facts,
            "recent_topics": list(set(self.recent_topics[-10:])),  # Unique recent topics
            "session_info": session_info,
            "conversation_length": session_info["message_count"] if session_info else 0
        }
        
    async def search_memory(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search through conversation history in SQLite"""
        if not self.enable_search:
            return []
        
        results = await self.sqlite_manager.search_conversations(
            query=query,
            limit=limit,
            session_id=self.current_session_id  # Search within current session
        )
        
        logger.debug(f"🔍 Found {len(results)} results for query: {query}")
        return results
        
    async def get_conversation_summary(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get a summary of conversation history"""
        session_id = session_id or self.current_session_id
        
        # Get full history for summary
        history = await self.sqlite_manager.get_conversation_history(
            session_id=session_id,
            limit=self.max_history
        )
        
        # Get session info
        session_info = await self.sqlite_manager.get_session_info(session_id)
        
        # Calculate basic stats
        user_messages = [m for m in history if m["role"] == "user"]
        assistant_messages = [m for m in history if m["role"] == "assistant"]
        
        # Extract unique speakers
        speakers = list(set(m.get("speaker_id") for m in user_messages if m.get("speaker_id")))
        
        return {
            "session_id": session_id,
            "message_count": len(history),
            "user_message_count": len(user_messages),
            "assistant_message_count": len(assistant_messages),
            "speakers": speakers,
            "user_facts": self.user_facts,
            "recent_topics": list(set(self.recent_topics[-10:])),
            "duration_seconds": (
                time.time() - session_info["start_time"] 
                if session_info and session_info.get("start_time") 
                else 0
            ),
            "recent_messages": history[-10:] if history else []
        }
    
    async def cleanup(self):
        """Clean up resources when module is unloaded"""
        # End current session
        await self.sqlite_manager.end_session(self.current_session_id)
        
        # Close SQLite connection
        await self.sqlite_manager.close()
        
        logger.info("🧹 Memory module cleaned up")

