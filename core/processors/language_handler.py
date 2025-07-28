# maestrocat/processors/language_handler.py
"""
Language handler for dynamic language switching
Manages system prompt updates based on language preference
"""

import logging
from typing import Dict, Any, Optional
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

logger = logging.getLogger(__name__)


class LanguageHandler:
    """Handles language changes and updates system prompts"""
    
    def __init__(self, context: OpenAILLMContext, event_emitter=None):
        self._context = context
        self._event_emitter = event_emitter
        self._current_language = 'en'
        self._language_prompts = self._create_language_prompts()
        
        # Subscribe to config changes if event emitter is available
        if self._event_emitter:
            self._event_emitter.subscribe("config_change", self._handle_config_change)
    
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
        
        logger.info(f"LanguageHandler received config change: {component} - {settings}")
        
        if component == "llm" and "response_language" in settings:
            await self._update_language(settings["response_language"])
        elif component == "stt" and "language" in settings:
            # Log STT language change
            logger.info(f"STT language changed to: {settings['language']}")
            # Don't update system prompt for STT changes
            pass
    
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