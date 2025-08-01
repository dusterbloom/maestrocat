# core/processors/amem_context_injector.py
"""
Injects relevant context from the Agentic Memory module into the LLM prompt.
"""
import logging
from typing import Dict, Any

from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

from ..modules.amem import AMemModule

logger = logging.getLogger(__name__)


class AMemContextInjector(FrameProcessor):
    """
    This processor intercepts user transcriptions, queries the AMemModule for
    relevant context, and prepends it to the user's message for the LLM.
    """

    def __init__(self, context: OpenAILLMContext, amem_module: AMemModule):
        super().__init__()
        self._context = context
        self._amem = amem_module

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """
        Intercepts TranscriptionFrames to inject context, and ensures all
        frames are passed through.
        """
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            user_text = frame.text
            logger.info(f"AMemContextInjector: Intercepted transcription: {user_text}")

            # Get relevant context from A-Mem
            retrieved_context = await self._amem.get_context(user_text)
            formatted_context = self._format_context_for_llm(retrieved_context)

            # Inject the context into the user's message
            if formatted_context:
                logger.info(f"AMemContextInjector: Injecting context:\n{formatted_context}")
                # The user's message is the last one in the context.
                last_message = self._context.messages[-1]
                if last_message["role"] == "user":
                    original_content = last_message["content"]
                    last_message["content"] = f"{formatted_context}\n\nUser query: {original_content}"
            else:
                logger.info("AMemContextInjector: No relevant context found.")

        # Crucially, always push the frame to the next processor
        await self.push_frame(frame, direction)

    def _format_context_for_llm(self, context: Dict[str, Any]) -> str:
        """
        Formats the retrieved memories into a string for the LLM.
        """
        if not context.get("semantic_matches") and not context.get("linked_memories"):
            return ""

        formatted = "[Recalled Memory Context]\n"
        
        # Add semantic matches
        if context.get("semantic_matches"):
            formatted += "Directly related memories:\n"
            for mem in context["semantic_matches"][:2]:  # Limit to top 2
                formatted += f"- {mem['metadata'].get('title', 'Memory')}: {mem['content']}\n"

        # Add linked memories
        if context.get("linked_memories"):
            formatted += "\nLinked memories:\n"
            for mem in context["linked_memories"][:2]: # Limit to top 2
                formatted += f"- {mem['metadata'].get('title', 'Memory')}: {mem['content']}\n"
        
        formatted += "[End of Memory Context]"
        return formatted
