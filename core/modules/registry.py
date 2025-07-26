"""
Module Registry - Central registry for module capabilities and discovery
"""
from typing import Dict, List, Type, Optional, Any, Set
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ModuleCapability:
    """Standard module capabilities"""
    CONVERSATION_MEMORY = "conversation_memory"
    CONTEXT_INJECTION = "context_injection"
    VOICE_RECOGNITION = "voice_recognition"
    EMOTION_DETECTION = "emotion_detection"
    METRICS_COLLECTION = "metrics_collection"
    AUDIO_PROCESSING = "audio_processing"
    INTERRUPTION_HANDLING = "interruption_handling"
    CUSTOM_COMMANDS = "custom_commands"


class ModuleRegistry:
    """
    Central registry for module capabilities and metadata.
    
    This registry:
    - Tracks available module classes and their capabilities
    - Provides module discovery by capability
    - Validates module interfaces
    - Manages module dependencies
    """
    
    def __init__(self):
        self.modules: Dict[str, Dict[str, Any]] = {}
        self._capability_index: Dict[str, Set[str]] = {}
        
    def register(self, module_class: Type['MaestroCatModule']):
        """
        Register a module class with its capabilities
        
        Args:
            module_class: The module class to register
            
        Raises:
            ValueError: If module doesn't implement required methods
        """
        # Validate module interface
        if not hasattr(module_class, 'get_capabilities'):
            raise ValueError(f"Module {module_class.__name__} must implement get_capabilities()")
            
        if not hasattr(module_class, 'get_hooks'):
            raise ValueError(f"Module {module_class.__name__} must implement get_hooks()")
            
        # Get module metadata
        module_name = module_class.__name__
        capabilities = module_class.get_capabilities()
        hooks = module_class.get_hooks()
        dependencies = getattr(module_class, 'get_dependencies', lambda: [])()
        
        # Store module information
        self.modules[module_name] = {
            'class': module_class,
            'capabilities': capabilities,
            'hooks': hooks,
            'dependencies': dependencies,
            'description': module_class.__doc__ or "No description provided"
        }
        
        # Update capability index
        for capability in capabilities:
            if capability not in self._capability_index:
                self._capability_index[capability] = set()
            self._capability_index[capability].add(module_name)
            
        logger.info(f"Registered module: {module_name} with capabilities: {capabilities}")
        
    def unregister(self, module_name: str):
        """
        Unregister a module from the registry
        
        Args:
            module_name: Name of the module to unregister
        """
        if module_name not in self.modules:
            logger.warning(f"Module {module_name} not found in registry")
            return
            
        # Remove from capability index
        module_info = self.modules[module_name]
        for capability in module_info['capabilities']:
            if capability in self._capability_index:
                self._capability_index[capability].discard(module_name)
                if not self._capability_index[capability]:
                    del self._capability_index[capability]
                    
        # Remove module
        del self.modules[module_name]
        logger.info(f"Unregistered module: {module_name}")
        
    def get_module_info(self, module_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a registered module
        
        Args:
            module_name: Name of the module
            
        Returns:
            Module information dictionary or None if not found
        """
        return self.modules.get(module_name)
        
    def get_modules_by_capability(self, capability: str) -> List[str]:
        """
        Find all modules that provide a specific capability
        
        Args:
            capability: The capability to search for
            
        Returns:
            List of module names that provide the capability
        """
        return list(self._capability_index.get(capability, set()))
        
    def get_all_capabilities(self) -> List[str]:
        """Get all registered capabilities"""
        return list(self._capability_index.keys())
        
    def get_all_modules(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered modules and their information"""
        return self.modules.copy()
        
    def validate_dependencies(self, module_name: str) -> tuple[bool, List[str]]:
        """
        Validate that all dependencies for a module are available
        
        Args:
            module_name: Name of the module to validate
            
        Returns:
            Tuple of (is_valid, missing_dependencies)
        """
        module_info = self.get_module_info(module_name)
        if not module_info:
            return False, [f"Module {module_name} not found"]
            
        dependencies = module_info.get('dependencies', [])
        missing = []
        
        for dep in dependencies:
            if dep not in self.modules:
                missing.append(dep)
                
        return len(missing) == 0, missing
        
    def get_load_order(self, module_names: List[str]) -> List[str]:
        """
        Determine the correct load order based on dependencies
        
        Args:
            module_names: List of modules to load
            
        Returns:
            Ordered list of module names
            
        Raises:
            ValueError: If circular dependencies detected
        """
        # Build dependency graph
        graph = {}
        for name in module_names:
            info = self.get_module_info(name)
            if info:
                graph[name] = info.get('dependencies', [])
                
        # Topological sort
        visited = set()
        stack = []
        
        def visit(node, path=None):
            if path is None:
                path = set()
                
            if node in path:
                raise ValueError(f"Circular dependency detected: {node}")
                
            if node not in visited:
                visited.add(node)
                path.add(node)
                
                for dep in graph.get(node, []):
                    if dep in module_names:  # Only consider requested modules
                        visit(dep, path)
                        
                path.remove(node)
                stack.append(node)
                
        for name in module_names:
            if name not in visited:
                visit(name)
                
        return stack
        
    def to_dict(self) -> Dict[str, Any]:
        """Export registry state as dictionary"""
        return {
            'modules': {
                name: {
                    'capabilities': info['capabilities'],
                    'hooks': {str(k): v for k, v in info['hooks'].items()},
                    'dependencies': info['dependencies'],
                    'description': info['description']
                }
                for name, info in self.modules.items()
            },
            'capability_index': {
                cap: list(modules)
                for cap, modules in self._capability_index.items()
            }
        }