# examples/basic_assistant.py
import asyncio
from core import MaestroCat
from core.modules import BaseModule

class GreetingModule(BaseModule):
    """Example module that adds personalized greetings"""
    
    def __init__(self, config):
        super().__init__("greeting", config)
        self.known_voices = {}
        
    async def on_pipeline_event(self, event):
        if event.event_type == "conversation_started":
            # Check if we recognize the voice
            speaker = self.known_voices.get(event.data.get('voice_id'))
            if speaker:
                greeting = f"Welcome back, {speaker}!"
            else:
                greeting = "Hello! I don't think we've met before."
                
            await self.emit_event("custom_greeting", {
                "text": greeting,
                "speaker": speaker
            })

async def main():
    # Initialize MaestroCat
    maestro = MaestroCat(
        config_file="config/basic_assistant.yaml",
        debug_ui=True
    )
    
    # Load a custom module
    await maestro.load_module(GreetingModule, {})
    
    # Set up conversation handler
    @maestro.on_conversation
    async def handle_conversation(transcript, response):
        print(f"User: {transcript}")
        print(f"Assistant: {response}")
        
    # Start the system
    print("Starting MaestroCat...")
    print("Debug UI available at http://localhost:8080")
    await maestro.start()

if __name__ == "__main__":
    asyncio.run(main())