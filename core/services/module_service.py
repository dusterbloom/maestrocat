"""
Module Service - Enhanced decoupled module management for MaestroCat
"""
from typing import Dict, List, Type, Optional, Any, Set, Callable
from abc import ABC, abstractmethod
import asyncio
import logging
from semantic_version import Version
import weakref
import threading

from ..modules.interface import (
    MaestroCatModule, ModuleMetadata, ModuleLifecycleState, 
    ModuleContext, ExtensionPoint
)
from ..modules.registry import ModuleRegistry
from ..context.pipeline_context import PipelineContext

logger = logging.getLogger(__name__)


class ModuleService:
    """
    Enhanced standalone service for managing modules independently of the pipeline.
    
    This service provides:
    - Complete module lifecycle management (load, unload, reload, hot-reload)
    - Dependency injection and resolution
    - Extension point management
    - Module versioning and compatibility checking
    - Event broadcasting without tight coupling
    - Thread-safe module operations
    - Module health monitoring
    """
    
    _instance: Optional['ModuleService'] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # Module management
        self.modules: Dict[str, MaestroCatModule] = {}
        self.registry = ModuleRegistry()
        self.pipeline_context = PipelineContext()
        
        # Service state
        self._running = False
        self._tasks: List[asyncio.Task] = []
        
        # Extension points
        self.extension_hooks: Dict[ExtensionPoint, List[Callable]] = {
            point: [] for point in ExtensionPoint
        }
        
        # Event subscribers (replaces EventEmitter)
        self._event_subscribers: Dict[str, Set[Callable]] = {}
        
        # Module health tracking
        self._module_health: Dict[str, Dict[str, Any]] = {}
        
        # Dependency injection container
        self._dependency_container: Dict[str, Any] = {}
    
    @classmethod
    def get_instance(cls) -> 'ModuleService':
        """Get singleton instance of ModuleService"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
        
    # Service Lifecycle
    
    async def start(self) -> bool:
        """Start the module service independently of pipeline"""
        with self._lock:
            if self._running:
                logger.warning("Module service already running")
                return True
                
            logger.info("Starting module service")
            self._running = True
        
        # Initialize all loaded modules in dependency order
        try:
            module_names = list(self.modules.keys())
            load_order = self.registry.get_load_order(module_names)
            
            for module_name in load_order:
                if module_name in self.modules:
                    module = self.modules[module_name]
                    success = await self._initialize_module(module_name, module)
                    if not success:
                        logger.error(f"Failed to initialize module: {module_name}")
            
            logger.info("Module service started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start module service: {e}")
            self._running = False
            return False
    
    async def stop(self) -> bool:
        """Stop the module service and cleanup"""
        with self._lock:
            if not self._running:
                return True
                
            logger.info("Stopping module service")
            self._running = False
        
        # Stop all modules in reverse dependency order
        try:
            module_names = list(self.modules.keys())
            stop_order = list(reversed(self.registry.get_load_order(module_names)))
            
            for module_name in stop_order:
                if module_name in self.modules:
                    module = self.modules[module_name]
                    await self._stop_module(module_name, module)
            
            # Cancel any running tasks
            for task in self._tasks:
                if not task.done():
                    task.cancel()
            
            logger.info("Module service stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping module service: {e}")
            return False
    
    # Module Registration and Discovery
    
    def register_module_class(self, module_class: Type[MaestroCatModule]) -> bool:
        """Register a module class with the registry"""
        try:
            self.registry.register(module_class)
            logger.info(f"Registered module class: {module_class.__name__}")
            return True
        except Exception as e:
            logger.error(f"Failed to register module class {module_class.__name__}: {e}")
            return False
    
    # Enhanced Module Lifecycle Management
    
    async def load_module(
        self, 
        module_name: str, 
        config: Optional[Dict[str, Any]] = None,
        instance_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Load and initialize a module instance
        
        Args:
            module_name: Name of the registered module class
            config: Optional configuration for the module
            instance_name: Optional custom instance name
            
        Returns:
            Instance name if successfully loaded, None otherwise
        """
        with self._lock:
            # Validate module exists in registry
            module_info = self.registry.get_module_info(module_name)
            if not module_info:
                logger.error(f"Module {module_name} not found in registry")
                return None
            
            # Generate instance name
            if not instance_name:
                instance_name = f"{module_name}_{len([n for n in self.modules.keys() if n.startswith(module_name)])}"
            
            if instance_name in self.modules:
                logger.error(f"Module instance {instance_name} already exists")
                return None
        
        try:
            # Validate dependencies
            is_valid, missing_deps = self.registry.validate_dependencies(module_name)
            if not is_valid:
                logger.error(f"Missing dependencies for {module_name}: {missing_deps}")
                return None
            
            # Validate configuration
            module_class = module_info['class']
            config = config or {}
            validation_errors = module_class.validate_config(config) if hasattr(module_class, 'validate_config') else []
            if validation_errors:
                logger.error(f"Configuration validation failed for {module_name}: {validation_errors}")
                return None
            
            # Create module context
            module_context = ModuleContext(
                module_name=instance_name,
                config=config,
                pipeline_context=self.pipeline_context,
                shared_data=self._dependency_container,
                logger=logging.getLogger(f"maestrocat.module.{instance_name}")
            )
            
            # Create module instance
            module = module_class(module_context)
            
            # Store module instance
            with self._lock:
                self.modules[instance_name] = module
                self._update_module_health(instance_name, "loaded", True)
            
            # Initialize if service is running
            if self._running:
                success = await self._initialize_module(instance_name, module)
                if not success:
                    with self._lock:
                        del self.modules[instance_name]
                    return None
            
            logger.info(f"Loaded module: {instance_name}")
            return instance_name
            
        except Exception as e:
            logger.error(f"Failed to load module {module_name}: {e}")
            return None
    
    async def unload_module(self, instance_name: str) -> bool:
        """Unload and cleanup a module instance"""
        with self._lock:
            if instance_name not in self.modules:
                logger.error(f"Module instance {instance_name} not found")
                return False
            
            module = self.modules[instance_name]
        
        try:
            # Stop the module
            await self._stop_module(instance_name, module)
            
            # Remove from registry and cleanup
            with self._lock:
                del self.modules[instance_name]
                self._module_health.pop(instance_name, None)
            
            logger.info(f"Unloaded module: {instance_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unload module {instance_name}: {e}")
            return False
    
    async def reload_module(self, instance_name: str) -> bool:
        """Hot-reload a module instance"""
        with self._lock:
            if instance_name not in self.modules:
                logger.error(f"Module instance {instance_name} not found")
                return False
            
            module = self.modules[instance_name]
            config = module.config.copy()
            module_class_name = module.__class__.__name__
        
        # Unload the module
        success = await self.unload_module(instance_name)
        if not success:
            return False
        
        # Reload the module with same configuration
        new_instance = await self.load_module(module_class_name, config, instance_name)
        return new_instance is not None
    
    # Module Access and Discovery
    
    def get_module(self, instance_name: str) -> Optional[MaestroCatModule]:
        """Get a specific module instance by name"""
        with self._lock:
            return self.modules.get(instance_name)
    
    def get_active_modules(self) -> List[MaestroCatModule]:
        """Get all active (running state) module instances"""
        with self._lock:
            return [
                module for module in self.modules.values() 
                if module.get_state() == ModuleLifecycleState.RUNNING
            ]
    
    def get_modules_by_capability(self, capability: str) -> List[MaestroCatModule]:
        """Get all modules that provide a specific capability"""
        modules = []
        for instance_name, module in self.modules.items():
            module_info = self.registry.get_module_info(module.__class__.__name__)
            if module_info and capability in [cap.value for cap in module_info['capabilities']]:
                modules.append(module)
        return modules
    
    def list_modules(self) -> Dict[str, Dict[str, Any]]:
        """List all loaded modules with their status"""
        with self._lock:
            return {
                name: {
                    "class": module.__class__.__name__,
                    "state": module.get_state().value,
                    "health": self._module_health.get(name, {}),
                    "config": module.config
                }
                for name, module in self.modules.items()
            }
    
    # Extension Point Management
    
    def register_extension_hook(
        self, 
        point: ExtensionPoint, 
        handler: Callable,
        module_name: Optional[str] = None
    ) -> None:
        """Register a handler for an extension point"""
        with self._lock:
            if point not in self.extension_hooks:
                self.extension_hooks[point] = []
            
            # Store handler with metadata
            hook_info = {
                'handler': handler,
                'module_name': module_name,
                'registered_at': asyncio.get_event_loop().time()
            }
            self.extension_hooks[point].append(hook_info)
            
            logger.debug(f"Registered extension hook for {point.value} from {module_name}")
    
    async def execute_extension_point(
        self, 
        point: ExtensionPoint, 
        context: PipelineContext
    ) -> PipelineContext:
        """Execute all handlers for an extension point"""
        handlers = []
        with self._lock:
            handlers = self.extension_hooks.get(point, []).copy()
        
        for hook_info in handlers:
            try:
                handler = hook_info['handler']
                context = await handler(point, context)
            except Exception as e:
                module_name = hook_info.get('module_name', 'unknown')
                logger.error(f"Error in extension point {point.value} handler from {module_name}: {e}")
        
        return context
    
    # Event System (replaces EventEmitter)
    
    def subscribe_to_event(self, event_type: str, callback: Callable) -> None:
        """Subscribe to an event type"""
        with self._lock:
            if event_type not in self._event_subscribers:
                self._event_subscribers[event_type] = set()
            self._event_subscribers[event_type].add(callback)
    
    def unsubscribe_from_event(self, event_type: str, callback: Callable) -> None:
        """Unsubscribe from an event type"""
        with self._lock:
            if event_type in self._event_subscribers:
                self._event_subscribers[event_type].discard(callback)
    
    async def emit_event(self, event_type: str, data: Any) -> None:
        """Emit an event to all subscribers"""
        # Add to pipeline context
        self.pipeline_context.add_event(event_type, data)
        
        # Get subscribers
        subscribers = set()
        with self._lock:
            # Specific event subscribers
            subscribers.update(self._event_subscribers.get(event_type, set()))
            # Wildcard subscribers
            subscribers.update(self._event_subscribers.get("*", set()))
        
        # Call subscribers
        if subscribers:
            tasks = []
            for callback in subscribers:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        task = asyncio.create_task(callback(event_type, data))
                        tasks.append(task)
                    else:
                        callback(event_type, data)
                except Exception as e:
                    logger.error(f"Error in event callback for {event_type}: {e}")
            
            # Wait for async callbacks
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    # Dependency Injection
    
    def register_dependency(self, name: str, instance: Any) -> None:
        """Register a dependency in the injection container"""
        with self._lock:
            self._dependency_container[name] = instance
            logger.debug(f"Registered dependency: {name}")
    
    def get_dependency(self, name: str) -> Optional[Any]:
        """Get a dependency from the injection container"""
        with self._lock:
            return self._dependency_container.get(name)
    
    # Context Management
    
    def get_pipeline_context(self) -> PipelineContext:
        """Get the shared pipeline context"""
        return self.pipeline_context
    
    # Internal Helper Methods
    
    async def _initialize_module(self, instance_name: str, module: MaestroCatModule) -> bool:
        """Initialize a module instance"""
        try:
            # Set state to initializing
            module._set_state(ModuleLifecycleState.INITIALIZING)
            
            # Inject dependencies
            await self._inject_dependencies(instance_name, module)
            
            # Initialize module
            success = await module.initialize()
            if not success:
                module._set_state(ModuleLifecycleState.ERROR)
                return False
            
            # Set state to initialized
            module._set_state(ModuleLifecycleState.INITIALIZED)
            
            # Start module
            success = await module.start()
            if not success:
                module._set_state(ModuleLifecycleState.ERROR)
                return False
            
            # Set state to running
            module._set_state(ModuleLifecycleState.RUNNING)
            
            # Register extension hooks
            await self._register_module_hooks(instance_name, module)
            
            self._update_module_health(instance_name, "initialized", True)
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize module {instance_name}: {e}")
            module._set_state(ModuleLifecycleState.ERROR)
            self._update_module_health(instance_name, "error", False, str(e))
            return False
    
    async def _stop_module(self, instance_name: str, module: MaestroCatModule) -> bool:
        """Stop a module instance"""
        try:
            # Set state to stopping
            module._set_state(ModuleLifecycleState.STOPPING)
            
            # Unregister extension hooks
            await self._unregister_module_hooks(instance_name, module)
            
            # Stop module
            success = await module.stop()
            if not success:
                logger.warning(f"Module {instance_name} reported stop failure")
            
            # Set state to stopped
            module._set_state(ModuleLifecycleState.STOPPED)
            
            self._update_module_health(instance_name, "stopped", True)
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop module {instance_name}: {e}")
            module._set_state(ModuleLifecycleState.ERROR)
            self._update_module_health(instance_name, "error", False, str(e))
            return False
    
    async def _inject_dependencies(self, instance_name: str, module: MaestroCatModule) -> None:
        """Inject dependencies into a module"""
        metadata = module.__class__.get_metadata()
        
        for dep_name in metadata.dependencies:
            # Try to find dependency in other modules
            dep_module = self.get_module(dep_name)
            if dep_module:
                module.set_dependency(dep_name, dep_module)
            else:
                # Try dependency injection container
                dep_instance = self.get_dependency(dep_name)
                if dep_instance:
                    module.set_dependency(dep_name, dep_instance)
                else:
                    logger.warning(f"Dependency {dep_name} not found for module {instance_name}")
    
    async def _register_module_hooks(self, instance_name: str, module: MaestroCatModule) -> None:
        """Register module's extension point hooks"""
        metadata = module.__class__.get_metadata()
        
        for extension_point in metadata.extension_points:
            handler = lambda point, ctx: module.handle_extension_point(point, ctx)
            self.register_extension_hook(extension_point, handler, instance_name)
    
    async def _unregister_module_hooks(self, instance_name: str, module: MaestroCatModule) -> None:
        """Unregister module's extension point hooks"""
        with self._lock:
            for point, hooks in self.extension_hooks.items():
                self.extension_hooks[point] = [
                    hook for hook in hooks 
                    if hook.get('module_name') != instance_name
                ]
    
    def _update_module_health(
        self, 
        module_name: str, 
        operation: str, 
        success: bool, 
        error: Optional[str] = None
    ) -> None:
        """Update module health tracking"""
        with self._lock:
            if module_name not in self._module_health:
                self._module_health[module_name] = {
                    'operations': [],
                    'last_error': None,
                    'error_count': 0
                }
            
            health = self._module_health[module_name]
            health['operations'].append({
                'operation': operation,
                'success': success,
                'timestamp': asyncio.get_event_loop().time(),
                'error': error
            })
            
            # Keep only recent operations
            if len(health['operations']) > 50:
                health['operations'] = health['operations'][-25:]
            
            if error:
                health['last_error'] = error
                health['error_count'] += 1