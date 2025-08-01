# maestrocat/services/ollama_llm.py
"""Ollama LLM Service for Pipecat"""
import asyncio
import json
import httpx
import time
from typing import AsyncGenerator, Optional, Dict, Any, List, TYPE_CHECKING
import logging
from pipecat.frames.frames import Frame, TextFrame, LLMFullResponseStartFrame, LLMFullResponseEndFrame
from pipecat.services.llm_service import LLMService
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext, OpenAILLMContextFrame
from pipecat.processors.aggregators.llm_response import LLMUserContextAggregator, LLMAssistantContextAggregator

if TYPE_CHECKING:
    from ..modules.amem import AMemModule

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
        temperature: float = 0.7,
        max_tokens: int = 1000,
        top_p: float = 0.9,
        top_k: int = 40,
        repetition_penalty: float = 1.1,
        event_emitter=None,
        amem_module: "Optional[AMemModule]" = None,
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
        self._amem = amem_module
        
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

    async def _decide_tool_use(self, context: OpenAILLMContext) -> Dict[str, Any]:
        """First LLM call to decide if a tool is needed."""
        logger.info("OLLamaLLMService: Deciding on tool use...")
        
        decision_context = context.get_messages()
        user_query = decision_context[-1]["content"]

        tool_prompt = f"""
        You are a helpful AI assistant with access to a memory tool.
        Your task is to decide if you need to use the memory tool to answer the user's query.

        User Query: "{user_query}"

        Do you need to consult your memory to answer this query? The memory contains past conversations and user preferences.
        Use the memory tool if the user is asking a question about themselves, their preferences, or something mentioned in the past.

        Respond with a single JSON object.
        If you need to use the memory tool, respond with:
        {{"tool": "memory", "query": "a search query for the memory system"}}

        If you do not need to use the tool, respond with:
        {{"tool": "none", "answer": "your direct answer to the user"}}
        """
        
        # Replace the user's message with a new list of messages for the decision prompt
        decision_messages = [
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": tool_prompt}
        ]

        response = await self.generate(decision_messages, stream=False)
        
        try:
            decision = json.loads(response)
            logger.info(f"OLLamaLLMService: Tool use decision: {decision}")
            return decision
        except json.JSONDecodeError:
            logger.error(f"Failed to parse tool use decision: {response}")
            return {"tool": "none", "answer": "I'm having trouble with my internal tools right now."}

    async def _generate_final_answer(self, context: OpenAILLMContext, memory_results: str) -> AsyncGenerator[Frame, None]:
        """Second LLM call to synthesize a final answer with memory context."""
        logger.info("OLLamaLLMService: Synthesizing final answer with memory context...")
        
        user_query = context.get_messages()[-2]["content"]

        synthesis_prompt = f"""
        You are a helpful AI assistant.
        You were asked the following question: "{user_query}"
        You have retrieved the following information from your memory:
        
        [Recalled Memory Context]
        {memory_results}
        [End of Memory Context]

        Based on this context, please provide a helpful and conversational answer to the user.
        """
        
        synthesis_context = OpenAILLMContext()
        synthesis_context.add_message({"role": "system", "content": "You are a helpful AI assistant."})
        synthesis_context.add_message({"role": "user", "content": synthesis_prompt})

        async for frame in self._stream_chat_completion(synthesis_context):
            yield frame

    async def get_chat_completions(self, context: OpenAILLMContext) -> AsyncGenerator[Frame, None]:
        """Main entry point for the tool-using agent logic."""
        if not self._amem:
            logger.warning("AMemModule not available. Falling back to simple generation.")
            async for frame in self._stream_chat_completion(context):
                yield frame
            return

        decision = await self._decide_tool_use(context)

        if decision.get("tool") == "memory":
            search_query = decision.get("query", context.get_messages()[-1]["content"])
            memory_results = await self._amem.search(search_query)
            
            if not memory_results:
                formatted_results = "No relevant memories found."
            else:
                formatted_results = "\n".join([f"- {m['content']}" for m in memory_results])

            async for frame in self._generate_final_answer(context, formatted_results):
                yield frame
        else:
            answer = decision.get("answer", "I'm not sure how to respond to that.")
            yield TextFrame(answer)

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

    async def generate(self, messages: List[Dict[str, str]], stream: bool = False) -> str:
        """Generic method to call Ollama, supporting streaming or single response."""
        logger.info(f"OLLamaLLMService: Generating text with model {self._model}")
        logger.debug(f"OLLamaLLMService: Request messages: {messages}")
        try:
            response = await self._client.post(
                f"{self._base_url}/api/chat",
                json={"model": self._model, "messages": messages, "stream": stream},
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
            raise
        except Exception as e:
            logger.error(f"OLLamaLLMService: Error generating text: {e}")
            return ""

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
