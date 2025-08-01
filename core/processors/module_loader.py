# maestrocat/processors/module_loader.py
"""Module system for extending pipelines at runtime"""
from .event_emitter import EventEmitter
from typing import Dict, Any, List, Optional, Type
import logging
import json
from abc import ABC, abstractmethod

from pipecat.frames.frames import Frame, SystemFrame, TextFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

from ..modules.base import MaestroCatModule

logger = logging.getLogger(__name__)

        

class ModuleLoader(FrameProcessor):
    """
    Loads and manages modules that extend pipeline functionality
    Modules can listen to events and modify context
    """
    
    def __init__(self, event_emitter: Optional[EventEmitter] = None):
        super().__init__()
        self.modules: Dict[str, MaestroCatModule] = {}
        self.event_emitter = event_emitter
        # Store event wrappers for cleanup
        self._event_wrappers: Dict[str, Any] = {}
        
    async def load_module(
        self,
        module_class: Type[MaestroCatModule],
        config: Dict[str, Any]
    ) -> MaestroCatModule:
        """Load a module into the system"""
        module_name = config.get("name", module_class.__name__)
        
        try:
            # Create module instance
            module = module_class(module_name, config)
            
            # Pass event emitter reference if module supports it
            if self.event_emitter:
                if hasattr(module, 'set_event_emitter'):
                    module.set_event_emitter(self.event_emitter)
                # For older modules that might just have the attribute
                elif hasattr(module, '_event_emitter'):
                    module._event_emitter = self.event_emitter
            
            # Initialize
            await module.initialize()
            
            # Store module
            self.modules[module_name] = module
            
            # Subscribe to events if event emitter provided and module has on_event
            if self.event_emitter and hasattr(module, 'on_event'):
                # Create a wrapper that always passes event_type and data separately
                # This is the standard MaestroCatModule interface
                async def module_event_wrapper(event):
                    event_type = event.get("type", "")
                    data = event.get("data", {})
                    await module.on_event(event_type, data)
                
                # Store wrapper for cleanup
                self._event_wrappers[module_name] = module_event_wrapper
                self.event_emitter.subscribe("*", module_event_wrapper)
                
            logger.info(f"Loaded module: {module_name}")
            
            # Don't emit frames during setup - the pipeline hasn't started yet
            # If we need to notify about module loading, use the event emitter instead
            if self.event_emitter:
                await self.event_emitter.emit("module_loaded", {
                    "name": module_name,
                    "config": config
                })
            
            return module
            
        except Exception as e:
            logger.error(f"Failed to load module {module_name}: {e}")
            raise
    
    def register_module(self, module: MaestroCatModule):
        """Register an already initialized module"""
        module_name = module.name
        
        # Store module
        self.modules[module_name] = module
        
        # Subscribe to events if event emitter provided and module has on_event
        if self.event_emitter and hasattr(module, 'on_event'):
            # Create a wrapper that always passes event_type and data separately
            async def module_event_wrapper(event):
                event_type = event.get("type", "")
                data = event.get("data", {})
                await module.on_event(event_type, data)
            
            # Store wrapper for cleanup
            self._event_wrappers[module_name] = module_event_wrapper
            self.event_emitter.subscribe("*", module_event_wrapper)
        
        # Pass event emitter reference if module doesn't have it
        if self.event_emitter and hasattr(module, 'event_emitter') and not module.event_emitter:
            module.event_emitter = self.event_emitter
            
        logger.info(f"Registered module: {module_name}")
            
    async def unload_module(self, module_name: str):
        """Unload a module"""
        if module_name in self.modules:
            module = self.modules[module_name]
            
            # Cleanup
            await module.cleanup()
            
            # Unsubscribe from events
            if self.event_emitter and module_name in self._event_wrappers:
                self.event_emitter.unsubscribe("*", self._event_wrappers[module_name])
                del self._event_wrappers[module_name]
                
            # Remove module
            del self.modules[module_name]
            
            logger.info(f"Unloaded module: {module_name}")
            
            # Use event emitter instead of frames during setup/teardown
            if self.event_emitter:
                await self.event_emitter.emit("module_unloaded", {
                    "name": module_name
                })
            
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