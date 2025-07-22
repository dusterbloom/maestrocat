# maestrocat/services/ollama_llm.py
"""Ollama LLM Service for Pipecat"""
import json
import httpx
from typing import AsyncGenerator, Optional, Dict, Any
import logging

from pipecat.frames.frames import Frame, TextFrame, LLMFullResponseStartFrame, LLMFullResponseEndFrame
from pipecat.services.ai_services import LLMService
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

logger = logging.getLogger(__name__)


class OllamaLLMService(LLMService):
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
        
    async def _generate_chat_completion(
        self,
        context: OpenAILLMContext
    ) -> AsyncGenerator[Frame, None]:
        """Generate completion from Ollama"""
        
        try:
            # Prepare request
            messages = context.get_messages()
            
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
                    context.add_message("assistant", full_response)
                    
            # End response
            yield LLMFullResponseEndFrame()
            
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            raise
            
    async def stop(self):
        """Cleanup HTTP client"""
        await super().stop()
        await self._client.aclose()
