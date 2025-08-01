# maestrocat/services/ollama_llm.py
"""Ollama LLM Service for Pipecat"""
import asyncio
import json
import httpx
import time
from typing import AsyncGenerator, Optional, Dict, Any, List
import logging
from pipecat.frames.frames import Frame, TextFrame, LLMFullResponseStartFrame, LLMFullResponseEndFrame
from pipecat.services.llm_service import LLMService
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext, OpenAILLMContextFrame
from pipecat.processors.aggregators.llm_response import LLMUserContextAggregator, LLMAssistantContextAggregator

logger = logging.getLogger(__name__)


class OLLamaLLMService(LLMService):
    """
    Ollama integration for Pipecat that acts as a tool-using agent.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2:3b",
        temperature: float = 0.3,
        max_tokens: int = 100,
        top_p: float = 0.9,
        top_k: int = 40,
        repetition_penalty: float = 1.1,
        event_emitter=None,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self._base_url = base_url
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._top_p = top_p
        self._top_k = top_k
        self._repetition_penalty = repetition_penalty
        self._event_emitter = event_emitter
        
        self._client = httpx.AsyncClient(
            limits=httpx.Limits(max_keepalive_connections=1, max_connections=2),
            timeout=httpx.Timeout(10.0, connect=1.0, read=10.0)
        )
        self._model_loaded = False

    def create_context_aggregator(self, context: OpenAILLMContext):
        """Create context aggregators for user and assistant messages"""
        user_aggregator = LLMUserContextAggregator(context=context)
        assistant_aggregator = LLMAssistantContextAggregator(context=context)
        
        class ContextAggregatorPair:
            def user(self): return user_aggregator
            def assistant(self): return assistant_aggregator
        
        return ContextAggregatorPair()


    async def get_chat_completions(self, context: OpenAILLMContext) -> AsyncGenerator[Frame, None]:
        """Generate chat completions using the context (which may already include memory)."""
        # Simply use the context as-is - AMemContextInjector handles memory injection
        async for frame in self._stream_chat_completion(context):
            yield frame

    async def _stream_chat_completion(self, context: OpenAILLMContext) -> AsyncGenerator[Frame, None]:
        """Handles the actual streaming of the response from Ollama."""
        messages = context.get_messages()
        request_data = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": self._temperature}
        }
        
        full_response = ""
        async with self._client.stream("POST", f"{self._base_url}/api/chat", json=request_data) as response:
            async for line in response.aiter_lines():
                if not line: continue
                try:
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        token = data["message"]["content"]
                        full_response += token
                        yield TextFrame(token)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse streaming line: {line}")
        
        context.add_message({"role": "assistant", "content": full_response})

    async def generate(self, messages: List[Dict[str, str]], stream: bool = False, response_format: Dict[str, Any] = None) -> str:
        """
        Generic method to call Ollama, supporting streaming or single response.
        
        Args:
            messages: List of messages in OpenAI format
            stream: Whether to stream the response
            response_format: Optional JSON schema format (for structured outputs)
        """
        logger.info(f"OLLamaLLMService: Generating text with model {self._model}")
        logger.debug(f"OLLamaLLMService: Request messages: {messages}")
        
        request_data = {
            "model": self._model, 
            "messages": messages, 
            "stream": stream
        }
        
        # Add JSON mode if response format is specified
        if response_format:
            # Ollama uses format="json" for JSON mode
            request_data["format"] = "json"
            
            # Add system message to enforce JSON response if not already present
            has_system_msg = any(msg.get("role") == "system" for msg in messages)
            if not has_system_msg:
                messages = [{
                    "role": "system",
                    "content": "You must respond with a valid JSON object."
                }] + messages
                request_data["messages"] = messages
        
        try:
            response = await self._client.post(
                f"{self._base_url}/api/chat",
                json=request_data,
                timeout=30.0
            )
            logger.debug(f"OLLamaLLMService: Response status code: {response.status_code}")
            logger.debug(f"OLLamaLLMService: Response content: {response.text}")
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except httpx.HTTPStatusError as e:
            logger.error(f"OLLamaLLMService: HTTP error generating text: {e}")
            logger.error(f"OLLamaLLMService: Response content: {e.response.text}")
            # Return empty JSON if format was requested
            return "{}" if response_format else ""
        except Exception as e:
            logger.error(f"OLLamaLLMService: Error generating text: {e}")
            # Return empty JSON if format was requested
            return "{}" if response_format else ""

    async def process_frame(self, frame: Frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, OpenAILLMContextFrame):
            try:
                await self.push_frame(LLMFullResponseStartFrame())
                async for response_frame in self.get_chat_completions(frame.context):
                    await self.push_frame(response_frame, direction)
            finally:
                await self.push_frame(LLMFullResponseEndFrame())
        else:
            await self.push_frame(frame, direction)
