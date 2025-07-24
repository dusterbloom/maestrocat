# maestrocat/services/ollama_llm.py
"""Ollama LLM Service for Pipecat"""
import json
import httpx
from typing import AsyncGenerator, Optional, Dict, Any
import logging

from pipecat.frames.frames import Frame, TextFrame, LLMFullResponseStartFrame, LLMFullResponseEndFrame, TranscriptionFrame
from pipecat.services.llm_service import LLMService
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext, OpenAILLMContextFrame
from pipecat.processors.aggregators.llm_response import LLMUserContextAggregator, LLMAssistantContextAggregator

logger = logging.getLogger(__name__)


class OLLamaLLMService(LLMService):
    """
    Ollama integration for Pipecat
    Provides local LLM inference using Ollama
    """
    
    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2:3b",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        top_p: float = 0.9,
        top_k: int = 40,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self._base_url = base_url
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._top_p = top_p
        self._top_k = top_k
        
        self._client = httpx.AsyncClient(timeout=60.0)
        
    def create_context_aggregator(self, context: OpenAILLMContext):
        """Create context aggregators for user and assistant messages"""
        
        class ContextAggregatorPair:
            def __init__(self, user_agg, assistant_agg):
                self._user = user_agg
                self._assistant = assistant_agg
                
            def user(self):
                return self._user
                
            def assistant(self):
                return self._assistant
        
        user_aggregator = LLMUserContextAggregator(context=context)
        assistant_aggregator = LLMAssistantContextAggregator(context=context)
        
        return ContextAggregatorPair(user_aggregator, assistant_aggregator)
        
    async def _generate_chat_completion(
        self,
        context: OpenAILLMContext
    ) -> AsyncGenerator[Frame, None]:
        """Generate completion from Ollama"""
        
        try:
            # Prepare request
            messages = context.get_messages()
            logger.info(f"🤖 Ollama starting generation with {len(messages)} messages")
            logger.info(f"🤖 Full context messages: {messages}")
            if messages:
                logger.info(f"🤖 Last message: {messages[-1]['content'][:100]}...")
            
            request_data = {
                "model": self._model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": self._temperature,
                    "top_p": self._top_p,
                    "top_k": self._top_k,
                    "num_predict": self._max_tokens,
                }
            }
            
            # Start response
            yield LLMFullResponseStartFrame()
            
            # Stream response
            async with self._client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=request_data
            ) as response:
                response.raise_for_status()
                
                full_response = ""
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                        
                    try:
                        data = json.loads(line)
                        
                        if "error" in data:
                            logger.error(f"Ollama error: {data['error']}")
                            break
                            
                        # Extract token
                        if "message" in data and "content" in data["message"]:
                            token = data["message"]["content"]
                            if token:
                                full_response += token
                                yield TextFrame(token)
                                
                        # Check if done
                        if data.get("done", False):
                            break
                            
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse: {line}")
                        
                # Update context with response
                if full_response:
                    from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContextMessage
                    context.add_message(OpenAILLMContextMessage.create_assistant_message(full_response))
                    
            # End response
            yield LLMFullResponseEndFrame()
            
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            raise
            
    async def process_frame(self, frame: Frame, direction):
        """Process frames and handle OpenAILLMContextFrame for generation"""
        
        # Call parent first
        await super().process_frame(frame, direction)
        
        # Handle OpenAILLMContextFrame to trigger generation
        if isinstance(frame, OpenAILLMContextFrame):
            logger.info(f"🤖 LLM received OpenAILLMContextFrame - triggering generation!")
            context = frame.context
            logger.info(f"🤖 Context has {len(context.get_messages())} messages")
            
            try:
                # Start the generation process
                await self.push_frame(LLMFullResponseStartFrame(), direction)
                
                # Generate response
                async for response_frame in self._generate_chat_completion(context):
                    await self.push_frame(response_frame, direction)
                    
                # End the generation
                await self.push_frame(LLMFullResponseEndFrame(), direction)
                
            except Exception as e:
                logger.error(f"🤖 Generation failed: {e}")
                raise
        else:
            # For other frames, just push them through
            await self.push_frame(frame, direction)
    
    async def stop(self):
        """Cleanup HTTP client"""
        await super().stop()
        await self._client.aclose()
