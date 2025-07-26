# maestrocat/services/ollama_llm.py
"""Ollama LLM Service for Pipecat"""
import asyncio
import json
import httpx
import time
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
        event_emitter = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self._base_url = base_url
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._top_p = top_p
        self._top_k = top_k
        self._event_emitter = event_emitter
        
        # Optimized HTTP client with connection pooling
        self._client = httpx.AsyncClient(
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            timeout=httpx.Timeout(30.0, connect=2.0, read=30.0)
        )
        
        # Pre-load model on initialization
        self._model_loaded = False
        
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
    
    async def _preload_model(self):
        """Pre-load model and keep it warm for instant responses"""
        if self._model_loaded:
            return
            
        try:
            logger.info(f"🚀 Pre-loading and warming up model {self._model}...")
            
            # First ensure model is downloaded
            await self._client.post(
                f"{self._base_url}/api/pull",
                json={"model": self._model},
                timeout=120.0
            )
            
            # Warm up the model with a proper generation request
            response = await self._client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": "Say 'ready' to confirm you're loaded"}],
                    "keep_alive": "60m",  # Keep model loaded for 1 hour
                    "stream": False,
                    "options": {
                        "num_predict": 5,  # Generate a few tokens to fully warm up
                        "temperature": 0.1,
                        "num_ctx": 2048,
                        "num_batch": 1024,
                        "num_threads": -1
                    }
                },
                timeout=30.0
            )
            response.raise_for_status()
            self._model_loaded = True
            logger.info(f"✅ Model {self._model} pre-loaded, warmed up, and ready for instant responses")
        except Exception as e:
            logger.warning(f"⚠️ Model pre-loading failed: {e}")
            # Continue anyway - model will load on first request
        
    async def _generate_chat_completion(
        self,
        context: OpenAILLMContext
    ) -> AsyncGenerator[Frame, None]:
        """Generate completion from Ollama with optimized streaming"""
        
        # Ensure model is pre-loaded
        await self._preload_model()
        
        try:
            # Prepare request
            messages = context.get_messages()
            
            request_data = {
                "model": self._model,
                "messages": messages,
                "stream": True,
                "keep_alive": "60m",  # Keep model loaded for 1 hour
                "options": {
                    "temperature": self._temperature,
                    "top_p": self._top_p,
                    "top_k": self._top_k,
                    "num_predict": self._max_tokens,
                    "num_ctx": 1024,  # Even smaller context for ultra-low latency
                    "num_batch": 512,  # Smaller batch for faster first token
                    "num_threads": -1,  # Use all cores
                    "num_gpu": -1,  # Use all GPU layers if available
                }
            }
            
            # Emit LLM response start event
            if self._event_emitter:
                await self._event_emitter.emit("llm_response_start", {
                    "model": self._model,
                    "timestamp": time.time()
                })
            
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
                            
                        # Extract token and stream immediately
                        if "message" in data and "content" in data["message"]:
                            token = data["message"]["content"]
                            if token:
                                full_response += token
                                
                                # Emit chunk event for debug UI
                                if self._event_emitter:
                                    await self._event_emitter.emit("llm_response_chunk", {
                                        "chunk": token,
                                        "timestamp": time.time()
                                    })
                                
                                yield TextFrame(token)
                                
                        # Check if done
                        if data.get("done", False):
                            break
                            
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse: {line}")
                        
                # Update context with response
                if full_response:
                    context.add_message({
                        "role": "assistant", 
                        "content": full_response
                    })
                    
                    # Emit completion event
                    if self._event_emitter:
                        await self._event_emitter.emit("llm_response_complete", {
                            "text": full_response,
                            "model": self._model,
                            "timestamp": time.time()
                        })
            
        except asyncio.CancelledError:
            logger.info("LLM generation cancelled - stopping immediately")
            raise
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            raise
    
    async def get_chat_completions(self, context: OpenAILLMContext) -> AsyncGenerator[Frame, None]:
        """Required method for LLMService base class"""
        async for frame in self._generate_chat_completion(context):
            yield frame
    
    async def process_frame(self, frame: Frame, direction):
        """Process frames for LLM completion requests"""
        await super().process_frame(frame, direction)
        
        if isinstance(frame, OpenAILLMContextFrame):
            context = frame.context
            
            # Emit transcription event for the user's message
            if self._event_emitter and context.messages:
                # Find the last user message in the context
                user_messages = [msg for msg in context.messages if msg.get("role") == "user"]
                if user_messages:
                    last_user_message = user_messages[-1]
                    user_text = last_user_message.get("content", "")
                    if user_text and user_text.strip():
                        await self._event_emitter.emit("transcription_final", {
                            "text": user_text,
                            "confidence": 1.0,
                            "timestamp": time.time(),
                            "user_id": "user"
                        })
            
            try:
                await self.push_frame(LLMFullResponseStartFrame())
                async for response_frame in self.get_chat_completions(context):
                    await self.push_frame(response_frame, direction)
            finally:
                await self.push_frame(LLMFullResponseEndFrame())
        else:
            await self.push_frame(frame, direction)
            
    
    async def stop(self):
        """Cleanup HTTP client"""
        await super().stop()
        await self._client.aclose()
