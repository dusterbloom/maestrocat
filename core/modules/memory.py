# maestrocat/modules/memory.py
"""Memory module for conversation history and context"""
from typing import Dict, Any, List, Optional
from collections import deque
import json
import os

from core.modules.base import MaestroCatModule


class MemoryModule(MaestroCatModule):
    """
    Memory module that stores conversation history
    and provides context enrichment
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        
        self.max_history = config.get("max_history", 100)
        self.save_to_disk = config.get("save_to_disk", False)
        self.memory_file = config.get("memory_file", "conversation_memory.json")
        
        # Memory storage
        self.short_term = deque(maxlen=self.max_history)
        self.long_term = {}
        self.user_facts = {}
        
        # Load existing memory if available
        if self.save_to_disk and os.path.exists(self.memory_file):
            self._load_memory()
            
    async def on_event(self, event_type: str, data: Any):
        """Process events to build memory"""
        if event_type == "transcription_complete":
            # Store user utterance
            self.short_term.append({
                "type": "user",
                "text": data.get("text", ""),
                "timestamp": data.get("timestamp"),
                "metadata": data
            })
            
            # Extract facts (simple keyword extraction for demo)
            await self._extract_facts(data.get("text", ""))
            
        elif event_type == "llm_response_complete":
            # Store assistant response
            self.short_term.append({
                "type": "assistant", 
                "text": data.get("text", ""),
                "timestamp": data.get("timestamp")
            })
            
        # Periodically save to disk
        if self.save_to_disk and len(self.short_term) % 10 == 0:
            self._save_memory()
            
    async def _extract_facts(self, text: str):
        """Extract facts from user utterances"""
        # Simple extraction for demo
        # In production, use NLP/NER
        
        text_lower = text.lower()
        
        # Extract name
        if "my name is" in text_lower:
            name = text.split("my name is")[-1].strip().split()[0]
            self.user_facts["name"] = name
            
        # Extract preferences
        if "i like" in text_lower:
            like = text.split("i like")[-1].strip()
            if "likes" not in self.user_facts:
                self.user_facts["likes"] = []
            self.user_facts["likes"].append(like)
            
    def get_context(self, num_turns: int = 5) -> Dict[str, Any]:
        """Get relevant context for LLM"""
        recent_history = list(self.short_term)[-num_turns:]
        
        return {
            "recent_history": recent_history,
            "user_facts": self.user_facts,
            "conversation_length": len(self.short_term)
        }
        
    def search_memory(self, query: str) -> List[Dict]:
        """Search through conversation history"""
        results = []
        query_lower = query.lower()
        
        for memory in self.short_term:
            if query_lower in memory.get("text", "").lower():
                results.append(memory)
                
        return results
        
    def _save_memory(self):
        """Save memory to disk"""
        memory_data = {
            "short_term": list(self.short_term),
            "user_facts": self.user_facts,
            "long_term": self.long_term
        }
        
        with open(self.memory_file, "w") as f:
            json.dump(memory_data, f)
            
    def _load_memory(self):
        """Load memory from disk"""
        try:
            with open(self.memory_file, "r") as f:
                memory_data = json.load(f)
                
            self.short_term = deque(memory_data.get("short_term", []), maxlen=self.max_history)
            self.user_facts = memory_data.get("user_facts", {})
            self.long_term = memory_data.get("long_term", {})
            
        except Exception as e:
            logger.error(f"Failed to load memory: {e}")

