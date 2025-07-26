"""
Pipeline Context API - Shared context for decoupled module communication
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import threading


@dataclass
class Message:
    """Represents a conversation message"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineContext:
    """
    Shared context for pipeline and modules.
    
    This context provides a decoupled way for modules to:
    - Access conversation history
    - Share data between modules
    - Modify pipeline behavior
    - Store persistent state
    
    Thread-safe for concurrent access.
    """
    
    def __init__(self):
        # Core conversation state
        self.conversation_history: List[Message] = []
        self.current_transcription: Optional[str] = None
        self.llm_response: Optional[str] = None
        self.is_interrupted: bool = False
        self.interruption_context: Optional[str] = None
        
        # Pipeline metadata
        self.metadata: Dict[str, Any] = {}
        
        # Module-specific data storage
        self.module_data: Dict[str, Any] = {}
        
        # Performance metrics
        self.metrics: Dict[str, float] = {
            'stt_latency': 0.0,
            'llm_latency': 0.0,
            'tts_latency': 0.0,
            'total_latency': 0.0
        }
        
        # Thread safety
        self._lock = threading.RLock()
        
    # Conversation Management
    
    def add_user_message(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Add a user message to conversation history"""
        with self._lock:
            message = Message(
                role="user",
                content=content,
                metadata=metadata or {}
            )
            self.conversation_history.append(message)
            self.current_transcription = content
            
    def add_assistant_message(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Add an assistant message to conversation history"""
        with self._lock:
            message = Message(
                role="assistant",
                content=content,
                metadata=metadata or {}
            )
            self.conversation_history.append(message)
            self.llm_response = content
            
    def get_conversation_history(self, limit: Optional[int] = None) -> List[Message]:
        """Get conversation history with optional limit"""
        with self._lock:
            if limit:
                return self.conversation_history[-limit:]
            return self.conversation_history.copy()
            
    def clear_conversation_history(self):
        """Clear all conversation history"""
        with self._lock:
            self.conversation_history.clear()
            self.current_transcription = None
            self.llm_response = None
            
    # Module Data Management
    
    def get_module_data(self, module_name: str, key: Optional[str] = None) -> Any:
        """
        Get data stored by a module
        
        Args:
            module_name: Name of the module
            key: Optional specific key within module data
            
        Returns:
            Module data or specific value if key provided
        """
        with self._lock:
            module_data = self.module_data.get(module_name, {})
            if key:
                return module_data.get(key)
            return module_data
            
    def set_module_data(self, module_name: str, key: str, value: Any):
        """
        Set data for a module
        
        Args:
            module_name: Name of the module
            key: Key to store value under
            value: Value to store
        """
        with self._lock:
            if module_name not in self.module_data:
                self.module_data[module_name] = {}
            self.module_data[module_name][key] = value
            
    def update_module_data(self, module_name: str, data: Dict[str, Any]):
        """
        Update multiple values for a module
        
        Args:
            module_name: Name of the module
            data: Dictionary of key-value pairs to update
        """
        with self._lock:
            if module_name not in self.module_data:
                self.module_data[module_name] = {}
            self.module_data[module_name].update(data)
            
    # Metadata Management
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata value"""
        with self._lock:
            return self.metadata.get(key, default)
            
    def set_metadata(self, key: str, value: Any):
        """Set metadata value"""
        with self._lock:
            self.metadata[key] = value
            
    def update_metadata(self, data: Dict[str, Any]):
        """Update multiple metadata values"""
        with self._lock:
            self.metadata.update(data)
            
    # Metrics Management
    
    def update_metric(self, metric_name: str, value: float):
        """Update a performance metric"""
        with self._lock:
            self.metrics[metric_name] = value
            
    def get_metrics(self) -> Dict[str, float]:
        """Get all performance metrics"""
        with self._lock:
            return self.metrics.copy()
            
    # Interruption Management
    
    def set_interrupted(self, interrupted: bool, context: Optional[str] = None):
        """Set interruption state and optional context"""
        with self._lock:
            self.is_interrupted = interrupted
            self.interruption_context = context
            
    def get_interruption_state(self) -> tuple[bool, Optional[str]]:
        """Get current interruption state and context"""
        with self._lock:
            return self.is_interrupted, self.interruption_context
            
    # Context Serialization
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize context to dictionary"""
        with self._lock:
            return {
                'conversation_history': [
                    {
                        'role': msg.role,
                        'content': msg.content,
                        'timestamp': msg.timestamp.isoformat(),
                        'metadata': msg.metadata
                    }
                    for msg in self.conversation_history
                ],
                'current_transcription': self.current_transcription,
                'llm_response': self.llm_response,
                'is_interrupted': self.is_interrupted,
                'interruption_context': self.interruption_context,
                'metadata': self.metadata,
                'module_data': self.module_data,
                'metrics': self.metrics
            }
            
    def from_dict(self, data: Dict[str, Any]):
        """Load context from dictionary"""
        with self._lock:
            # Clear existing data
            self.clear_conversation_history()
            self.metadata.clear()
            self.module_data.clear()
            
            # Load conversation history
            for msg_data in data.get('conversation_history', []):
                message = Message(
                    role=msg_data['role'],
                    content=msg_data['content'],
                    timestamp=datetime.fromisoformat(msg_data['timestamp']),
                    metadata=msg_data.get('metadata', {})
                )
                self.conversation_history.append(message)
                
            # Load other state
            self.current_transcription = data.get('current_transcription')
            self.llm_response = data.get('llm_response')
            self.is_interrupted = data.get('is_interrupted', False)
            self.interruption_context = data.get('interruption_context')
            self.metadata.update(data.get('metadata', {}))
            self.module_data.update(data.get('module_data', {}))
            self.metrics.update(data.get('metrics', {}))