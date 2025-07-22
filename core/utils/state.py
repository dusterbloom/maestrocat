# maestrocat/utils/state.py
"""Conversation state management"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import time


@dataclass
class Turn:
    """A single conversation turn"""
    speaker: str  # "user" or "assistant"
    text: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    

@dataclass
class ConversationState:
    """Manages conversation state"""
    session_id: str = ""
    turns: List[Turn] = field(default_factory=list)
    current_speaker: Optional[str] = None
    user_profile: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def add_turn(self, speaker: str, text: str, metadata: Optional[Dict] = None):
        """Add a conversation turn"""
        turn = Turn(
            speaker=speaker,
            text=text,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        self.turns.append(turn)
        
    def get_history(self, limit: Optional[int] = None) -> List[Turn]:
        """Get conversation history"""
        if limit:
            return self.turns[-limit:]
        return self.turns
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "session_id": self.session_id,
            "turns": [
                {
                    "speaker": t.speaker,
                    "text": t.text,
                    "timestamp": t.timestamp,
                    "metadata": t.metadata
                }
                for t in self.turns
            ],
            "current_speaker": self.current_speaker,
            "user_profile": self.user_profile,
            "context": self.context
        }
