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
        model: str = "gemma3:4b",
        temperature: float = 0.5,
        max_tokens: int = 200,
        top_p: float = 0.9,
        top_k: int = 40,
        repetition_penalty: float = 1.3,
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
        self._repetition_penalty = repetition_penalty
        self._event_emitter = event_emitter
        
        # Optimized HTTP client with minimal pooling for better performance
        self._client = httpx.AsyncClient(
            limits=httpx.Limits(max_keepalive_connections=1, max_connections=2),
            timeout=httpx.Timeout(10.0, connect=1.0, read=10.0)
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
            logger.info(f"🚀 Pre-loading model {self._model}...")
            
            # Skip redundant model pull - Ollama handles this automatically
            # Warm up with minimal, realistic request matching actual usage
            response = await self._client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "keep_alive": "60m",
                    "stream": False,
                    "options": {
                        "num_predict": 3,
                        "temperature": 0.1,
                        "num_ctx": 1024,     # Match actual usage
                        "num_batch": 512,    # Match actual usage
                        "num_threads": -1
                    }
                },
                timeout=10.0
            )
            response.raise_for_status()
            self._model_loaded = True
            logger.info(f"✅ Model {self._model} preloaded and ready")
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
        
        # Start timing
        llm_start_time = time.time()
        
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
                    "repetition_penalty": self._repetition_penalty,
                    "num_predict": self._max_tokens,
                    "num_ctx": 2048,  # Optimal context size for performance
                    "num_batch": 1024,  # Match context for optimal batching
                    "num_threads": -1,
                    "num_gpu": -1,
                    "stop": ["<|eot_id|>", "<|end_of_text|>", "\n\nUser:", "\n\nHuman:", "###", "<|im_end|>"]
                }
            }
            
            # Note: llm_response_start event will be emitted when first token arrives
            
            # Stream response
            async with self._client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=request_data
            ) as response:
                response.raise_for_status()
                
                full_response = ""
                first_token_received = False
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                        
                    try:
                        data = json.loads(line)
                        
                        if "error" in data:
                            logger.error(f"Ollama error: {data['error']}")
                            break
                        
                        # Check if response is complete
                        if data.get("done", False):
                            logger.debug("Ollama response marked as done")
                            break
                            
                        # Extract token and stream immediately
                        if "message" in data and "content" in data["message"]:
                            token = data["message"]["content"]
                            if token:
                                # Measure first token latency (key voice agent metric)
                                if not first_token_received:
                                    first_token_latency = (time.time() - llm_start_time) * 1000
                                    first_token_received = True
                                    
                                    # Emit essential events only on first token for performance
                                    if self._event_emitter:
                                        await self._event_emitter.emit("llm_response_start", {
                                            "model": self._model,
                                            "timestamp": time.time(),
                                            "first_token_latency_ms": first_token_latency
                                        })
                                        logger.info(f"📊 First token: {first_token_latency:.1f}ms")
                                
                                full_response += token
                                
                                # Reduce event emission overhead - only emit chunks for debugging if needed
                                # if self._event_emitter:
                                #     await self._event_emitter.emit("llm_response_chunk", {
                                #         "chunk": token,
                                #         "timestamp": time.time()
                                #     })
                                
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
