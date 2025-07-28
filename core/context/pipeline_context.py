"""
Pipeline Context API - Enhanced shared context for decoupled module communication
"""
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading
import logging

logger = logging.getLogger(__name__)


class ContextScope(Enum):
    """Scope levels for context data"""
    PIPELINE = "pipeline"        # Available to entire pipeline
    CONVERSATION = "conversation"  # Available for current conversation
    REQUEST = "request"          # Available for current request only
    MODULE = "module"           # Module-specific data


@dataclass
class Message:
    """Represents a conversation message"""
    content: str
    role: str  # 'user', 'assistant', 'system'
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    speaker_id: Optional[str] = None
    emotion: Optional[str] = None
    confidence: Optional[float] = None


@dataclass
class TranscriptionData:
    """STT transcription data"""
    text: str
    confidence: float
    language: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    audio_duration: Optional[float] = None
    speaker_id: Optional[str] = None
    is_partial: bool = False


@dataclass
class LLMResponse:
    """LLM response data"""
    text: str
    model: str
    tokens_used: int
    timestamp: datetime = field(default_factory=datetime.now)
    response_time: Optional[float] = None
    temperature: Optional[float] = None
    finish_reason: Optional[str] = None


@dataclass
class TTSData:
    """TTS synthesis data"""
    text: str
    voice: str
    audio_data: Optional[bytes] = None
    audio_format: str = "wav"
    sample_rate: int = 24000
    timestamp: datetime = field(default_factory=datetime.now)
    synthesis_time: Optional[float] = None


class PipelineContext:
    """
    Enhanced shared context for pipeline and modules.
    
    This class provides:
    - Thread-safe access to shared data
    - Scoped data management (pipeline, conversation, request, module)
    - Rich conversation state tracking
    - Event history
    - Module-specific data storage
    - Performance metrics
    - Error tracking
    
    Thread-safe for concurrent access across modules and pipeline.
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # Enhanced conversation data
        self.conversation_history: List[Message] = []
        self.current_transcription: Optional[TranscriptionData] = None
        self.current_llm_response: Optional[LLMResponse] = None
        self.current_tts_data: Optional[TTSData] = None
        
        # Context data organized by scope
        self._data: Dict[ContextScope, Dict[str, Any]] = {
            scope: {} for scope in ContextScope
        }
        
        # Module-specific data storage
        self._module_data: Dict[str, Dict[str, Any]] = {}
        
        # Event tracking
        self._events: List[Dict[str, Any]] = []
        
        # Conversation metadata
        self.conversation_id: Optional[str] = None
        self.conversation_start_time: datetime = datetime.now()
        self.last_activity_time: datetime = datetime.now()
        self.user_id: Optional[str] = None
        self.session_metadata: Dict[str, Any] = {}
        
        # Pipeline state
        self.is_interrupted: bool = False
        self.interruption_count: int = 0
        self.interruption_context: Optional[str] = None
        self.pipeline_errors: List[Dict[str, Any]] = []
        
        # Performance metrics
        self.metrics: Dict[str, float] = {
            'stt_latency': 0.0,
            'llm_latency': 0.0,
            'tts_latency': 0.0,
            'total_latency': 0.0
        }
        
    # Enhanced Scoped Data Management
    
    def set_data(
        self, 
        key: str, 
        value: Any, 
        scope: ContextScope = ContextScope.REQUEST
    ) -> None:
        """Set data in the specified scope"""
        with self._lock:
            self._data[scope][key] = value
            self.last_activity_time = datetime.now()
    
    def get_data(
        self, 
        key: str, 
        scope: ContextScope = ContextScope.REQUEST,
        default: Any = None
    ) -> Any:
        """Get data from the specified scope"""
        with self._lock:
            return self._data[scope].get(key, default)
    
    def has_data(self, key: str, scope: ContextScope = ContextScope.REQUEST) -> bool:
        """Check if data exists in the specified scope"""
        with self._lock:
            return key in self._data[scope]
    
    def remove_data(self, key: str, scope: ContextScope = ContextScope.REQUEST) -> bool:
        """Remove data from the specified scope"""
        with self._lock:
            if key in self._data[scope]:
                del self._data[scope][key]
                return True
            return False
    
    def clear_scope(self, scope: ContextScope) -> None:
        """Clear all data in a scope"""
        with self._lock:
            self._data[scope].clear()
    
    # Enhanced Module Data Management
    
    def set_module_data(self, module_name: str, key: str, value: Any) -> None:
        """Set module-specific data"""
        with self._lock:
            if module_name not in self._module_data:
                self._module_data[module_name] = {}
            self._module_data[module_name][key] = value
            self.last_activity_time = datetime.now()
    
    def get_module_data(
        self, 
        module_name: str, 
        key: Optional[str] = None, 
        default: Any = None
    ) -> Any:
        """Get module-specific data"""
        with self._lock:
            module_data = self._module_data.get(module_name, {})
            if key is None:
                return module_data
            return module_data.get(key, default)
    
    def has_module_data(self, module_name: str, key: str) -> bool:
        """Check if module has specific data"""
        with self._lock:
            return (module_name in self._module_data and 
                   key in self._module_data[module_name])
    
    def clear_module_data(self, module_name: str) -> None:
        """Clear all data for a module"""
        with self._lock:
            if module_name in self._module_data:
                self._module_data[module_name].clear()
    
    # Enhanced Conversation Management
    
    def add_user_message(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Add a user message to conversation history"""
        with self._lock:
            message = Message(
                role="user",
                content=content,
                metadata=metadata or {}
            )
            self.conversation_history.append(message)
            self.last_activity_time = datetime.now()
            
    def add_assistant_message(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Add an assistant message to conversation history"""
        with self._lock:
            message = Message(
                role="assistant",
                content=content,
                metadata=metadata or {}
            )
            self.conversation_history.append(message)
            self.last_activity_time = datetime.now()
    
    def add_message(self, message: Message) -> None:
        """Add a message to conversation history"""
        with self._lock:
            self.conversation_history.append(message)
            self.last_activity_time = datetime.now()
    
    def get_conversation_history(self, limit: Optional[int] = None) -> List[Message]:
        """Get conversation history with optional limit"""
        with self._lock:
            if limit and limit > 0:
                return self.conversation_history[-limit:]
            return self.conversation_history.copy()
    
    def get_messages_by_role(self, role: str, limit: Optional[int] = None) -> List[Message]:
        """Get messages by role (user, assistant, system)"""
        with self._lock:
            messages = [msg for msg in self.conversation_history if msg.role == role]
            return messages[-limit:] if limit and limit > 0 else messages
    
    # Event Management
    
    def add_event(self, event_type: str, data: Any) -> None:
        """Add an event to the event history"""
        with self._lock:
            event = {
                "type": event_type,
                "data": data,
                "timestamp": datetime.now(),
                "id": len(self._events)
            }
            self._events.append(event)
            
            # Keep only recent events to prevent memory bloat
            if len(self._events) > 1000:
                self._events = self._events[-500:]  # Keep last 500 events
    
    def get_events(
        self, 
        event_type: Optional[str] = None, 
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get events with optional filtering"""
        with self._lock:
            events = self._events.copy()
            
            # Filter by type
            if event_type:
                events = [e for e in events if e["type"] == event_type]
            
            # Filter by timestamp
            if since:
                events = [e for e in events if e["timestamp"] > since]
            
            # Apply limit
            if limit and limit > 0:
                events = events[-limit:]
            
            return events
    
    # Enhanced Interruption Management
    
    def set_interruption(self, interrupted: bool = True, context: Optional[str] = None) -> None:
        """Set interruption state"""
        with self._lock:
            if interrupted and not self.is_interrupted:
                self.interruption_count += 1
            self.is_interrupted = interrupted
            self.interruption_context = context
            self.last_activity_time = datetime.now()
    
    def get_interruption_state(self) -> tuple[bool, Optional[str], int]:
        """Get current interruption state, context, and count"""
        with self._lock:
            return self.is_interrupted, self.interruption_context, self.interruption_count
    
    # Error Management
    
    def add_error(self, error: Exception, context: str = "") -> None:
        """Add an error to the pipeline error list"""
        with self._lock:
            error_info = {
                "error": str(error),
                "type": type(error).__name__,
                "context": context,
                "timestamp": datetime.now()
            }
            self.pipeline_errors.append(error_info)
            
            # Keep only recent errors
            if len(self.pipeline_errors) > 100:
                self.pipeline_errors = self.pipeline_errors[-50:]
    
    # Metrics Management
    
    def update_metric(self, metric_name: str, value: float):
        """Update a performance metric"""
        with self._lock:
            self.metrics[metric_name] = value
            
    def get_metrics(self) -> Dict[str, float]:
        """Get all performance metrics"""
        with self._lock:
            return self.metrics.copy()
    
    # Context Lifecycle
    
    def reset_request_scope(self) -> None:
        """Reset request-scoped data (called between requests)"""
        with self._lock:
            self._data[ContextScope.REQUEST].clear()
            self.current_transcription = None
            self.current_llm_response = None
            self.current_tts_data = None
            self.is_interrupted = False
            self.interruption_context = None
    
    def reset_conversation_scope(self) -> None:
        """Reset conversation-scoped data (called between conversations)"""
        with self._lock:
            self._data[ContextScope.CONVERSATION].clear()
            self.conversation_history.clear()
            self._events.clear()
            self.conversation_start_time = datetime.now()
            self.last_activity_time = datetime.now()
            self.interruption_count = 0
            self.pipeline_errors.clear()
            self.conversation_id = None
            self.user_id = None
    
    def get_context_summary(self) -> Dict[str, Any]:
        """Get a summary of the current context"""
        with self._lock:
            return {
                "conversation_id": self.conversation_id,
                "message_count": len(self.conversation_history),
                "conversation_duration": (datetime.now() - self.conversation_start_time).total_seconds(),
                "last_activity": self.last_activity_time.isoformat(),
                "is_interrupted": self.is_interrupted,
                "interruption_count": self.interruption_count,
                "error_count": len(self.pipeline_errors),
                "current_transcription": self.current_transcription.text if self.current_transcription else None,
                "current_response": self.current_llm_response.text if self.current_llm_response else None,
                "active_modules": list(self._module_data.keys()),
                "pipeline_data_keys": list(self._data[ContextScope.PIPELINE].keys()),
                "conversation_data_keys": list(self._data[ContextScope.CONVERSATION].keys()),
                "request_data_keys": list(self._data[ContextScope.REQUEST].keys())
            }
    
    # Context Serialization
    
    def to_dict(self) -> Dict[str, Any]:
        """Export context as dictionary (for debugging/serialization)"""
        with self._lock:
            return {
                "conversation_id": self.conversation_id,
                "conversation_history": [
                    {
                        "content": msg.content,
                        "role": msg.role,
                        "timestamp": msg.timestamp.isoformat(),
                        "metadata": msg.metadata,
                        "speaker_id": msg.speaker_id,
                        "emotion": msg.emotion,
                        "confidence": msg.confidence
                    }
                    for msg in self.conversation_history
                ],
                "current_transcription": {
                    "text": self.current_transcription.text,
                    "confidence": self.current_transcription.confidence,
                    "timestamp": self.current_transcription.timestamp.isoformat(),
                    "language": self.current_transcription.language,
                    "speaker_id": self.current_transcription.speaker_id,
                    "is_partial": self.current_transcription.is_partial
                } if self.current_transcription else None,
                "current_llm_response": {
                    "text": self.current_llm_response.text,
                    "model": self.current_llm_response.model,
                    "tokens_used": self.current_llm_response.tokens_used,
                    "timestamp": self.current_llm_response.timestamp.isoformat(),
                    "response_time": self.current_llm_response.response_time
                } if self.current_llm_response else None,
                "scoped_data": {
                    scope.value: data.copy() 
                    for scope, data in self._data.items()
                },
                "module_data": {
                    module: data.copy() 
                    for module, data in self._module_data.items()
                },
                "events": self._events.copy(),
                "metrics": self.metrics.copy(),
                "metadata": self.get_context_summary()
            }