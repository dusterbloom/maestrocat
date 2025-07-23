# maestrocat/processors/module_loader.py
"""Module system for extending pipelines at runtime"""
from .event_emitter import EventEmitter
from typing import Dict, Any, List, Optional, Type
import logging
from abc import ABC, abstractmethod

from pipecat.frames.frames import Frame, SystemFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

logger = logging.getLogger(__name__)


class MaestroCatModule(ABC):
    """Base class for MaestroCat modules"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.enabled = True
        
    @abstractmethod
    async def on_event(self, event_type: str, data: Any):
        """Handle events from the pipeline"""
        pass
        
    async def initialize(self):
        """Initialize the module"""
        pass
        
    async def cleanup(self):
        """Cleanup when module is unloaded"""
        pass
        

class ModuleLoader(FrameProcessor):
    """
    Loads and manages modules that extend pipeline functionality
    Modules can listen to events and modify context
    """
    
    def __init__(self, event_emitter: Optional[EventEmitter] = None):
        super().__init__()
        self.modules: Dict[str, MaestroCatModule] = {}
        self.event_emitter = event_emitter
        
    async def load_module(
        self,
        module_class: Type[MaestroCatModule],
        config: Dict[str, Any]
    ):
        """Load a module into the system"""
        module_name = config.get("name", module_class.__name__)
        
        try:
            # Create module instance
            module = module_class(module_name, config)
            
            # Initialize
            await module.initialize()
            
            # Store module
            self.modules[module_name] = module
            
            # Subscribe to events if event emitter provided
            if self.event_emitter:
                self.event_emitter.subscribe("*", module.on_event)
                
            logger.info(f"Loaded module: {module_name}")
            
            # Emit module loaded event
            await self.push_frame(SystemFrame("module_loaded", {
                "name": module_name,
                "config": config
            }))
            
        except Exception as e:
            logger.error(f"Failed to load module {module_name}: {e}")
            raise
            
    async def unload_module(self, module_name: str):
        """Unload a module"""
        if module_name in self.modules:
            module = self.modules[module_name]
            
            # Cleanup
            await module.cleanup()
            
            # Unsubscribe from events
            if self.event_emitter:
                self.event_emitter.unsubscribe("*", module.on_event)
                
            # Remove module
            del self.modules[module_name]
            
            logger.info(f"Unloaded module: {module_name}")
            
            # Emit event
            await self.push_frame(SystemFrame("module_unloaded", {
                "name": module_name
            }))
            
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Allow modules to process frames"""
        # Let modules see all frames
        for module in self.modules.values():
            if module.enabled and hasattr(module, 'process_frame'):
                await module.process_frame(frame, direction)
                
        await self.push_frame(frame, direction)
        
    def get_module(self, name: str) -> Optional[MaestroCatModule]:
        """Get a loaded module by name"""
        return self.modules.get(name)
        
    def list_modules(self) -> List[str]:
        """List all loaded modules"""
        return list(self.modules.keys())