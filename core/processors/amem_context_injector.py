# core/processors/amem_context_injector.py
"""
Injects relevant context from the Agentic Memory module into the LLM prompt.
Uses a tiered search approach for optimal latency.
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional

from pipecat.frames.frames import Frame, TextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext, OpenAILLMContextFrame

from ..modules.amem import AMemModule

logger = logging.getLogger(__name__)


class AMemContextInjector(FrameProcessor):
    """
    This processor intercepts LLM message frames before they reach the LLM,
    queries the AMemModule for relevant context, and enriches the messages.
    """

    def __init__(self, amem_module: AMemModule):
        super().__init__()
        self._amem = amem_module
        self._session_id = None
        
        # Performance tracking
        self._total_searches = 0
        self._total_latency = 0.0
        
        # Cache the last query to avoid duplicate searches
        self._last_query = None
        self._last_context = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """
        Intercepts LLMMessagesFrame to inject context before LLM processing.
        """
        await super().process_frame(frame, direction)

        # Check if this is an OpenAI LLM context frame heading to the LLM
        if isinstance(frame, OpenAILLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            logger.info("AMemContextInjector: Intercepted OpenAILLMContextFrame")
            
            # Get the last user message from the context
            context = frame.context
            messages = context.get_messages()
            
            if messages and messages[-1]["role"] == "user":
                user_text = messages[-1]["content"]
                logger.info(f"AMemContextInjector: Processing user message: {user_text[:50]}...")
                
                # Check cache first to avoid duplicate searches
                if user_text == self._last_query and self._last_context:
                    logger.info("AMemContextInjector: Using cached context")
                    formatted_context = self._last_context
                else:
                    # Perform synchronous context retrieval - we MUST block here
                    # to ensure context is injected before LLM processes
                    formatted_context = await self._retrieve_and_format_context(user_text)
                    
                    # Cache the result
                    self._last_query = user_text
                    self._last_context = formatted_context
                
                # Inject context if found
                if formatted_context:
                    logger.info(f"AMemContextInjector: Injecting context into message")
                    # Inject context directly into the conversation without any labels
                    # This makes the LLM treat it as established facts rather than "memory"
                    original_content = messages[-1]["content"]
                    
                    # Create a natural context injection
                    # Add context as if it's part of the ongoing conversation
                    messages[-1]["content"] = f"{original_content}\n{formatted_context}"
                    
                    # The context is modified in place, so we just pass the frame through
                    logger.info(f"AMemContextInjector: Context injected successfully")
        
        # For all other frames, pass through unchanged
        await self.push_frame(frame, direction)
    
    async def _retrieve_and_format_context(self, user_text: str) -> Optional[str]:
        """
        Retrieve context from A-Mem and format it for injection.
        This is synchronous to ensure context is ready before LLM processing.
        """
        try:
            # Track search performance
            search_start = time.time()

            # Get relevant context using tiered search
            # Use only Tier 1 (SQLite) for fastest response
            retrieved_context = await self._amem.get_context(user_text, self._session_id)
            
            # Update metrics
            search_latency = (time.time() - search_start) * 1000  # ms
            self._total_searches += 1
            self._total_latency += search_latency
            
            # Log performance info
            tier_used = retrieved_context.get("tier_used", "none")
            tier_latency = retrieved_context.get("search_latency", 0)
            
            logger.info(f"AMemContextInjector: Search completed in {tier_latency:.2f}ms using {tier_used}")
            logger.info(f"  Results: {len(retrieved_context.get('tier1_matches', []))} tier1, {len(retrieved_context.get('semantic_matches', []))} semantic")
            
            # Format context based on tier results
            formatted_context = self._format_tiered_context(retrieved_context)
            
            if formatted_context:
                logger.info(f"AMemContextInjector: Formatted {len(formatted_context)} chars of context")
                logger.debug(f"Context preview: {formatted_context[:100]}...")
            else:
                logger.info("AMemContextInjector: No relevant context found")
                
            return formatted_context
                
        except Exception as e:
            logger.error(f"Error retrieving context: {e}", exc_info=True)
            return None
    
    def _format_tiered_context(self, context: Dict[str, Any]) -> str:
        """
        Formats context from tiered search results.
        Makes the context appear as natural facts in the conversation.
        """
        if not any([context.get("tier1_matches"), context.get("semantic_matches"), 
                   context.get("linked_memories")]):
            return ""
        
        # Build context as natural statements
        formatted_parts = []
        
        # Add tier 1 matches (keyword-based) - fastest
        if context.get("tier1_matches"):
            for mem in context["tier1_matches"][:2]:  # Limit to top 2
                # Extract the actual content from metadata
                content = mem.get('content', '')
                if content and len(content) > 15:  # Skip very short content
                    # Transform the content into a fact statement
                    # Remove any first-person references to make it third-person factual
                    fact = content.replace("I ", "You ").replace("my ", "your ").replace("me ", "you ")
                    formatted_parts.append(fact)
        
        # Add semantic matches (tier 2) only if no tier 1 matches
        elif context.get("semantic_matches"):
            for mem in context["semantic_matches"][:2]:  # Limit to top 2
                content = mem.get('content', '')
                if content and len(content) > 15:
                    fact = content.replace("I ", "You ").replace("my ", "your ").replace("me ", "you ")
                    formatted_parts.append(fact)
        
        # Add linked memories if we have space
        if context.get("linked_memories") and len(formatted_parts) < 4:
            for mem in context["linked_memories"][:1]:  # Just 1 linked memory
                content = mem.get('content', '')
                if content and len(content) > 15:
                    fact = content.replace("I ", "You ").replace("my ", "your ").replace("me ", "you ")
                    formatted_parts.append(fact)
        
        # Join as natural conversational context
        if formatted_parts:
            # Make it sound like established facts
            return "Previously mentioned: " + ". ".join(formatted_parts) + "."
        
        return ""
    
    def set_session_id(self, session_id: str):
        """Set the session ID for context retrieval."""
        self._session_id = session_id
        logger.info(f"AMemContextInjector: Session ID set to {session_id}")
    
    def get_performance_stats(self) -> Dict[str, float]:
        """Get performance statistics for the context injector."""
        avg_latency = self._total_latency / max(1, self._total_searches)
        return {
            "total_searches": self._total_searches,
            "average_latency_ms": avg_latency,
            "total_latency_ms": self._total_latency
        }