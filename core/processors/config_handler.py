# maestrocat/processors/config_handler.py
"""
Configuration handler processor for dynamic config updates
Handles language changes and updates system prompts accordingly
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from pipecat.frames.frames import Frame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

logger = logging.getLogger(__name__)


class ConfigHandler(FrameProcessor):
    """Handles configuration changes and updates pipeline components"""
    
    def __init__(self, context: OpenAILLMContext, event_emitter=None, **kwargs):
        super().__init__(**kwargs)
        self._context = context
        self._event_emitter = event_emitter
        self._current_language = 'en'
        self._language_prompts = self._create_language_prompts()
        self._config_change_task = None
    
    async def start_processing(self):
        """Start processing - subscribe to config changes"""
        await super().start_processing()
        
        # Subscribe to config changes if event emitter is available
        if self._event_emitter:
            self._config_change_task = asyncio.create_task(self._listen_for_config_changes())
    
    async def stop_processing(self):
        """Stop processing - clean up subscriptions"""
        if self._config_change_task:
            self._config_change_task.cancel()
            try:
                await self._config_change_task
            except asyncio.CancelledError:
                pass
        
        await super().stop_processing()
    
    async def _listen_for_config_changes(self):
        """Listen for config change events"""
        try:
            if self._event_emitter:
                await self._event_emitter.subscribe("config_change", self._handle_config_change)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in config change listener: {e}")
    
    def _create_language_prompts(self) -> Dict[str, str]:
        """Create language-specific system prompts"""
        return {
            'en': "You are MaestroCat, a helpful AI voice assistant. Keep responses brief and conversational. If interrupted, acknowledge it naturally.",
            'it': "Sei MaestroCat, un assistente vocale AI utile. Rispondi sempre in italiano. Mantieni le risposte brevi e conversazionali. Se vengo interrotto, riconoscilo naturalmente.",
            'fr': "Tu es MaestroCat, un assistant vocal IA utile. Réponds toujours en français. Garde tes réponses brèves et conversationnelles. Si tu es interrompu, reconnais-le naturellement.",
            'es': "Eres MaestroCat, un asistente de voz AI útil. Responde siempre en español. Mantén las respuestas breves y conversacionales. Si te interrumpen, reconócelo naturalmente.",
            'pt': "Você é MaestroCat, um assistente de voz AI útil. Responda sempre em português. Mantenha as respostas breves e conversacionais. Se for interrompido, reconheça naturalmente.",
            'ja': "あなたはMaestroCatという便利なAI音声アシスタントです。日本語で返答してください。回答は簡潔で会話的にしてください。中断された場合は自然に認識してください。",
            'zh': "你是MaestroCat，一个有用的AI语音助手。请用中文回复。保持回复简短和对话式。如果被打断，请自然地承认。"
        }
    
    async def _handle_config_change(self, event: Dict[str, Any]):
        """Handle configuration change events"""
        component = event.get("component")
        settings = event.get("settings", {})
        
        logger.info(f"ConfigHandler received config change: {component} - {settings}")
        
        if component == "llm" and "response_language" in settings:
            await self._update_language(settings["response_language"])
        elif component == "stt" and "language" in settings:
            # Also handle STT language changes for consistency
            language = settings["language"]
            if language != "auto":
                await self._update_language(language)
    
    async def _update_language(self, language: str):
        """Update the system prompt based on language"""
        if language == self._current_language:
            return
        
        self._current_language = language
        
        # Get the appropriate system prompt
        prompt = self._language_prompts.get(language, self._language_prompts['en'])
        
        # Update the context's system message
        if self._context and self._context.messages:
            # Find and update the system message
            for i, msg in enumerate(self._context.messages):
                if msg.get("role") == "system":
                    self._context.messages[i]["content"] = prompt
                    logger.info(f"Updated system prompt for language: {language}")
                    break
            else:
                # No system message found, add one
                self._context.messages.insert(0, {
                    "role": "system",
                    "content": prompt
                })
                logger.info(f"Added system prompt for language: {language}")
        
        # Emit language change event
        if self._event_emitter:
            await self._event_emitter.emit("language_changed", {
                "language": language,
                "prompt": prompt
            })
    
    async def process_frame(self, frame: Frame, direction):
        """Pass through all frames"""
        # Simply pass through all frames - we're just listening for config events
        await self.push_frame(frame, direction)