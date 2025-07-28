# core/modules/examples/enhanced_memory_module.py
"""
Enhanced Memory Module - Example implementation using new decoupled architecture
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import asyncio
from semantic_version import Version

from ..interface import (
    MaestroCatModule, ModuleMetadata, ExtensionPoint, ModuleCapability,
    ConversationMemoryInterface, ContextInjectionInterface
)
from ..registry import ModuleRegistry
from ...context.pipeline_context import PipelineContext, Message, ContextScope


class EnhancedMemoryModule(MaestroCatModule, ConversationMemoryInterface, ContextInjectionInterface):
    """
    Enhanced memory module demonstrating the new decoupled architecture.
    
    Features:
    - Implements multiple interfaces (ConversationMemoryInterface, ContextInjectionInterface)
    - Uses extension points for pipeline integration
    - Provides conversation memory and context injection capabilities
    - Supports configuration validation
    - Demonstrates proper lifecycle management
    """
    
    @classmethod
    def get_metadata(cls) -> ModuleMetadata:
        """Return module metadata"""
        return ModuleMetadata(
            name="EnhancedMemoryModule",
            version=Version("2.0.0"),
            description="Enhanced conversation memory with context injection capabilities",
            author="MaestroCat Team",
            capabilities=[
                ModuleCapability.CONVERSATION_MEMORY,
                ModuleCapability.CONTEXT_INJECTION,
                ModuleCapability.USER_PROFILING
            ],
            extension_points=[
                ExtensionPoint.POST_STT,
                ExtensionPoint.POST_LLM,
                ExtensionPoint.PRE_LLM
            ],
            dependencies=[],  # No dependencies for this example
            config_schema={
                "max_history": {"type": "integer", "default": 100, "minimum": 10},
                "save_to_disk": {"type": "boolean", "default": False},
                "memory_file": {"type": "string", "default": "conversation_memory.json"},
                "context_window": {"type": "integer", "default": 10, "minimum": 1},
                "enable_user_profiling": {"type": "boolean", "default": True},
                "semantic_search": {"type": "boolean", "default": False}
            }
        )
    
    def __init__(self, context):
        super().__init__(context)
        
        # Configuration
        config = self.config
        self.max_history = config.get("max_history", 100)
        self.save_to_disk = config.get("save_to_disk", False)
        self.memory_file = config.get("memory_file", "conversation_memory.json")
        self.context_window = config.get("context_window", 10)
        self.enable_user_profiling = config.get("enable_user_profiling", True)
        self.semantic_search = config.get("semantic_search", False)
        
        # Memory storage
        self.conversation_memory: List[Dict[str, Any]] = []
        self.user_profiles: Dict[str, Dict[str, Any]] = {}
        self.conversation_summaries: List[Dict[str, Any]] = []
        
        # Performance tracking
        self.memory_operations = 0
        self.last_cleanup = datetime.now()
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate module configuration"""
        errors = []
        
        if "max_history" in config:
            if not isinstance(config["max_history"], int) or config["max_history"] < 10:
                errors.append("max_history must be an integer >= 10")
        
        if "context_window" in config:
            if not isinstance(config["context_window"], int) or config["context_window"] < 1:
                errors.append("context_window must be an integer >= 1")
        
        if "memory_file" in config:
            if not isinstance(config["memory_file"], str) or not config["memory_file"].strip():
                errors.append("memory_file must be a non-empty string")
        
        return errors
    
    async def initialize(self) -> bool:
        """Initialize the memory module"""
        try:
            self.logger.info(f"Initializing {self.name} with config: {self.config}")
            
            # Load existing memory if configured
            if self.save_to_disk:
                await self._load_memory()
            
            # Initialize user profiling if enabled
            if self.enable_user_profiling:
                await self._initialize_user_profiling()
            
            self.logger.info(f"Memory module initialized with {len(self.conversation_memory)} stored memories")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize memory module: {e}")
            return False
    
    async def start(self) -> bool:
        """Start the memory module"""
        try:
            self.logger.info("Starting memory module")
            
            # Start background tasks if needed
            if self.save_to_disk:
                # Could start a periodic save task here
                pass
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start memory module: {e}")
            return False
    
    async def stop(self) -> bool:
        """Stop the memory module"""
        try:
            self.logger.info("Stopping memory module")
            
            # Save memory before stopping
            if self.save_to_disk:
                await self._save_memory()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop memory module: {e}")
            return False
    
    # Extension Point Handlers
    
    async def handle_extension_point(
        self, 
        point: ExtensionPoint, 
        context: PipelineContext
    ) -> PipelineContext:
        """Handle pipeline extension points"""
        try:
            if point == ExtensionPoint.POST_STT:
                # Store user message after STT
                if context.current_transcription:
                    await self._store_user_message(context)
                    
            elif point == ExtensionPoint.POST_LLM:
                # Store assistant message after LLM
                if context.current_llm_response:
                    await self._store_assistant_message(context)
                    
            elif point == ExtensionPoint.PRE_LLM:
                # Inject conversation context before LLM
                await self._inject_conversation_context(context)
            
            return context
            
        except Exception as e:
            self.logger.error(f"Error in extension point {point.value}: {e}")
            return context
    
    # ConversationMemoryInterface Implementation
    
    async def add_user_message(self, message: str, metadata: Dict[str, Any] = None) -> None:
        """Add a user message to memory"""
        memory_entry = {
            "role": "user",
            "content": message,
            "timestamp": datetime.now(),
            "metadata": metadata or {},
            "speaker_id": metadata.get("speaker_id") if metadata else None
        }
        
        self.conversation_memory.append(memory_entry)
        self.memory_operations += 1
        
        # Update user profile if enabled
        if self.enable_user_profiling and metadata:
            await self._update_user_profile(metadata.get("speaker_id", "default"), message, "user")
        
        # Cleanup old memories if needed
        await self._cleanup_memory()
        
        self.logger.debug(f"Added user message to memory: {message[:50]}...")
    
    async def add_assistant_message(self, message: str, metadata: Dict[str, Any] = None) -> None:
        """Add an assistant message to memory"""
        memory_entry = {
            "role": "assistant",
            "content": message,
            "timestamp": datetime.now(),
            "metadata": metadata or {}
        }
        
        self.conversation_memory.append(memory_entry)
        self.memory_operations += 1
        
        # Cleanup old memories if needed
        await self._cleanup_memory()
        
        self.logger.debug(f"Added assistant message to memory: {message[:50]}...")
    
    async def get_conversation_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent conversation history"""
        return self.conversation_memory[-limit:] if limit > 0 else self.conversation_memory.copy()
    
    async def search_memory(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search through conversation memory"""
        if not query.strip():
            return []
        
        query_lower = query.lower()
        results = []
        
        for memory in reversed(self.conversation_memory):  # Search most recent first
            content = memory.get("content", "").lower()
            if query_lower in content:
                results.append(memory.copy())
                if len(results) >= limit:
                    break
        
        self.logger.debug(f"Memory search for '{query}' returned {len(results)} results")
        return results
    
    # ContextInjectionInterface Implementation
    
    async def inject_context(self, context: PipelineContext) -> PipelineContext:
        """Inject additional context into the pipeline"""
        try:
            # Get relevant conversation history
            history = await self.get_conversation_history(self.context_window)
            
            # Get user profile if available
            user_profile = None
            if self.enable_user_profiling:
                # Try to get speaker ID from current transcription
                speaker_id = "default"
                if context.current_transcription and hasattr(context.current_transcription, 'speaker_id'):
                    speaker_id = context.current_transcription.speaker_id or "default"
                
                user_profile = self.user_profiles.get(speaker_id)
            
            # Inject context data
            context.set_data("conversation_history", history, ContextScope.REQUEST)
            context.set_data("user_profile", user_profile, ContextScope.REQUEST)
            context.set_data("memory_stats", {
                "total_memories": len(self.conversation_memory),
                "operations": self.memory_operations,
                "context_window": self.context_window
            }, ContextScope.REQUEST)
            
            self.logger.debug(f"Injected context: {len(history)} messages, user_profile: {user_profile is not None}")
            return context
            
        except Exception as e:
            self.logger.error(f"Failed to inject context: {e}")
            return context
    
    async def get_relevant_context(self, query: str) -> Dict[str, Any]:
        """Get context relevant to a query"""
        # Search for relevant memories
        relevant_memories = await self.search_memory(query, limit=5)
        
        # Get conversation summary if available
        summary = None
        if self.conversation_summaries:
            summary = self.conversation_summaries[-1]  # Most recent summary
        
        return {
            "relevant_memories": relevant_memories,
            "conversation_summary": summary,
            "total_memories": len(self.conversation_memory)
        }
    
    # Event Handlers
    
    async def handle_event(self, event_type: str, data: Any) -> None:
        """Handle custom events"""
        try:
            if event_type == "conversation_reset":
                await self._reset_conversation()
            elif event_type == "memory_cleanup":
                await self._cleanup_memory(force=True)
            elif event_type == "save_memory":
                if self.save_to_disk:
                    await self._save_memory()
            
        except Exception as e:
            self.logger.error(f"Error handling event {event_type}: {e}")
    
    # Interface Version Implementation
    
    def get_interface_version(self) -> Version:
        """Return the version of interface implementations"""
        return Version("1.0.0")
    
    # Private Helper Methods
    
    async def _store_user_message(self, context: PipelineContext) -> None:
        """Store user message from pipeline context"""
        if context.current_transcription:
            metadata = {
                "confidence": context.current_transcription.confidence,
                "language": context.current_transcription.language,
                "speaker_id": context.current_transcription.speaker_id,
                "audio_duration": context.current_transcription.audio_duration
            }
            await self.add_user_message(context.current_transcription.text, metadata)
    
    async def _store_assistant_message(self, context: PipelineContext) -> None:
        """Store assistant message from pipeline context"""
        if context.current_llm_response:
            metadata = {
                "model": context.current_llm_response.model,
                "tokens_used": context.current_llm_response.tokens_used,
                "response_time": context.current_llm_response.response_time,
                "finish_reason": context.current_llm_response.finish_reason
            }
            await self.add_assistant_message(context.current_llm_response.text, metadata)
    
    async def _inject_conversation_context(self, context: PipelineContext) -> None:
        """Inject conversation context before LLM processing"""
        await self.inject_context(context)
    
    async def _initialize_user_profiling(self) -> None:
        """Initialize user profiling system"""
        self.logger.info("User profiling enabled")
        # Could initialize NLP models or other profiling tools here
    
    async def _update_user_profile(self, speaker_id: str, message: str, role: str) -> None:
        """Update user profile based on new message"""
        if speaker_id not in self.user_profiles:
            self.user_profiles[speaker_id] = {
                "message_count": 0,
                "first_seen": datetime.now(),
                "last_seen": datetime.now(),
                "preferences": {},
                "topics": [],
                "sentiment_history": []
            }
        
        profile = self.user_profiles[speaker_id]
        profile["message_count"] += 1
        profile["last_seen"] = datetime.now()
        
        # Simple topic extraction (in production, use NLP)
        words = message.lower().split()
        common_topics = ["music", "food", "weather", "sports", "technology", "movies"]
        for topic in common_topics:
            if topic in words and topic not in profile["topics"]:
                profile["topics"].append(topic)
    
    async def _cleanup_memory(self, force: bool = False) -> None:
        """Clean up old memories if needed"""
        should_cleanup = (
            force or 
            len(self.conversation_memory) > self.max_history or
            (datetime.now() - self.last_cleanup).seconds > 300  # Every 5 minutes
        )
        
        if should_cleanup:
            if len(self.conversation_memory) > self.max_history:
                # Keep only the most recent memories
                self.conversation_memory = self.conversation_memory[-self.max_history:]
                self.logger.info(f"Cleaned up memory, now contains {len(self.conversation_memory)} entries")
            
            self.last_cleanup = datetime.now()
    
    async def _reset_conversation(self) -> None:
        """Reset conversation memory"""
        old_count = len(self.conversation_memory)
        self.conversation_memory.clear()
        self.logger.info(f"Reset conversation memory (cleared {old_count} entries)")
    
    async def _save_memory(self) -> None:
        """Save memory to disk"""
        try:
            memory_data = {
                "conversation_memory": [
                    {
                        **entry,
                        "timestamp": entry["timestamp"].isoformat() if isinstance(entry["timestamp"], datetime) else entry["timestamp"]
                    }
                    for entry in self.conversation_memory
                ],
                "user_profiles": {
                    speaker_id: {
                        **profile,
                        "first_seen": profile["first_seen"].isoformat() if isinstance(profile["first_seen"], datetime) else profile["first_seen"],
                        "last_seen": profile["last_seen"].isoformat() if isinstance(profile["last_seen"], datetime) else profile["last_seen"]
                    }
                    for speaker_id, profile in self.user_profiles.items()
                },
                "metadata": {
                    "saved_at": datetime.now().isoformat(),
                    "version": str(self.get_metadata().version),
                    "operations": self.memory_operations
                }
            }
            
            with open(self.memory_file, 'w') as f:
                json.dump(memory_data, f, indent=2)
            
            self.logger.info(f"Saved memory to {self.memory_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to save memory: {e}")
    
    async def _load_memory(self) -> None:
        """Load memory from disk"""
        try:
            import os
            if not os.path.exists(self.memory_file):
                self.logger.info(f"Memory file {self.memory_file} not found, starting fresh")
                return
            
            with open(self.memory_file, 'r') as f:
                memory_data = json.load(f)
            
            # Load conversation memory
            self.conversation_memory = []
            for entry in memory_data.get("conversation_memory", []):
                entry_copy = entry.copy()
                if "timestamp" in entry_copy:
                    entry_copy["timestamp"] = datetime.fromisoformat(entry_copy["timestamp"])
                self.conversation_memory.append(entry_copy)
            
            # Load user profiles
            self.user_profiles = {}
            for speaker_id, profile in memory_data.get("user_profiles", {}).items():
                profile_copy = profile.copy()
                if "first_seen" in profile_copy:
                    profile_copy["first_seen"] = datetime.fromisoformat(profile_copy["first_seen"])
                if "last_seen" in profile_copy:
                    profile_copy["last_seen"] = datetime.fromisoformat(profile_copy["last_seen"])
                self.user_profiles[speaker_id] = profile_copy
            
            # Load metadata
            metadata = memory_data.get("metadata", {})
            self.memory_operations = metadata.get("operations", 0)
            
            self.logger.info(f"Loaded memory from {self.memory_file}: {len(self.conversation_memory)} entries, {len(self.user_profiles)} profiles")
            
        except Exception as e:
            self.logger.error(f"Failed to load memory: {e}")