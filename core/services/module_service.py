"""
Module Service - Decoupled module management for MaestroCat
"""
from typing import Dict, List, Type, Optional, Any
from abc import ABC, abstractmethod
import asyncio
import logging

from ..modules.base import MaestroCatModule
from ..modules.registry import ModuleRegistry
from ..context.pipeline_context import PipelineContext

logger = logging.getLogger(__name__)


class ModuleService:
    """
    Standalone service for managing modules independently of the pipeline.
    
    This service handles:
    - Module lifecycle management (load, unload, reload)
    - Module registration and discovery
    - Context management for modules
    - Module communication without tight coupling
    """
    
    def __init__(self):
        self.modules: Dict[str, MaestroCatModule] = {}
        self.registry = ModuleRegistry()
        self.context_manager = PipelineContext()
        self._running = False
        self._tasks: List[asyncio.Task] = []
        
    async def start(self):
        """Start the module service independently of pipeline"""
        if self._running:
            logger.warning("Module service already running")
            return
            
        self._running = True
        logger.info("Starting module service")
        
        # Initialize all registered modules
        for module_name, module in self.modules.items():
            if module.enabled:
                try:
                    await module.initialize()
                    logger.info(f"Initialized module: {module_name}")
                except Exception as e:
                    logger.error(f"Failed to initialize module {module_name}: {e}")
                    
    async def stop(self):
        """Stop the module service and cleanup"""
        if not self._running:
            return
            
        self._running = False
        logger.info("Stopping module service")
        
        # Cleanup all modules
        for module_name, module in self.modules.items():
            try:
                await module.cleanup()
                logger.info(f"Cleaned up module: {module_name}")
            except Exception as e:
                logger.error(f"Error cleaning up module {module_name}: {e}")
                
        # Cancel any running tasks
        for task in self._tasks:
            task.cancel()
            
    def register_module_class(self, module_class: Type[MaestroCatModule]):
        """Register a module type with capabilities"""
        self.registry.register(module_class)
        logger.info(f"Registered module class: {module_class.__name__}")
        
    async def load_module(self, module_name: str, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Load and initialize a module instance
        
        Args:
            module_name: Name of the registered module class
            config: Optional configuration for the module
            
        Returns:
            True if successfully loaded, False otherwise
        """
        try:
            module_info = self.registry.get_module_info(module_name)
            if not module_info:
                logger.error(f"Module {module_name} not found in registry")
                return False
                
            # Create module instance
            module_class = module_info['class']
            module = module_class(config or {})
            
            # Store module instance
            instance_name = f"{module_name}_{id(module)}"
            self.modules[instance_name] = module
            
            # Initialize if service is running
            if self._running and module.enabled:
                await module.initialize()
                
            logger.info(f"Loaded module: {instance_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load module {module_name}: {e}")
            return False
            
    async def unload_module(self, instance_name: str) -> bool:
        """
        Unload and cleanup a module instance
        
        Args:
            instance_name: The instance name of the module to unload
            
        Returns:
            True if successfully unloaded, False otherwise
        """
        if instance_name not in self.modules:
            logger.error(f"Module instance {instance_name} not found")
            return False
            
        try:
            module = self.modules[instance_name]
            await module.cleanup()
            del self.modules[instance_name]
            logger.info(f"Unloaded module: {instance_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unload module {instance_name}: {e}")
            return False
            
    def get_active_modules(self) -> List[MaestroCatModule]:
        """Get all active (enabled) module instances"""
        return [m for m in self.modules.values() if m.enabled]
        
    def get_module(self, instance_name: str) -> Optional[MaestroCatModule]:
        """Get a specific module instance by name"""
        return self.modules.get(instance_name)
        
    def get_modules_by_capability(self, capability: str) -> List[MaestroCatModule]:
        """Get all modules that provide a specific capability"""
        modules = []
        for module in self.modules.values():
            module_info = self.registry.get_module_info(module.__class__.__name__)
            if module_info and capability in module_info['capabilities']:
                modules.append(module)
        return modules
        
    async def broadcast_event(self, event_type: str, data: Any):
        """
        Broadcast an event to all modules without tight coupling
        
        This replaces the EventEmitter dependency
        """
        tasks = []
        for module in self.get_active_modules():
            if hasattr(module, 'handle_event'):
                task = asyncio.create_task(
                    module.handle_event(event_type, data)
                )
                tasks.append(task)
                
        # Wait for all handlers to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    def get_context(self) -> PipelineContext:
        """Get the shared pipeline context"""
        return self.context_manager
        
    def update_context(self, updates: Dict[str, Any]):
        """Update the shared context"""
        for key, value in updates.items():
            setattr(self.context_manager, key, value)