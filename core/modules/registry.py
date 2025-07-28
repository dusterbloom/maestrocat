"""
Enhanced Module Registry - Central registry for module capabilities and discovery with versioning
"""
from typing import Dict, List, Type, Optional, Any, Set
import logging
from abc import ABC, abstractmethod
from semantic_version import Version
from .interface import ModuleMetadata, ModuleCapability, ExtensionPoint

logger = logging.getLogger(__name__)


class ModuleRegistry:
    """
    Enhanced central registry for module capabilities and metadata.
    
    This registry provides:
    - Module registration with versioning support
    - Capability-based module discovery
    - Dependency validation and resolution
    - Version compatibility checking
    - Interface validation
    - Module conflict detection
    """
    
    def __init__(self):
        # Module storage: module_name -> {version -> module_info}
        self.modules: Dict[str, Dict[str, Dict[str, Any]]] = {}
        
        # Indexes for fast lookup
        self._capability_index: Dict[ModuleCapability, Set[str]] = {}
        self._extension_point_index: Dict[ExtensionPoint, Set[str]] = {}
        self._dependency_graph: Dict[str, Set[str]] = {}
        
        # Version tracking
        self._latest_versions: Dict[str, Version] = {}
        
        # Interface registry for capability contracts
        self._interface_registry: Dict[str, Type] = {}
    
    def register(self, module_class: Type['MaestroCatModule']) -> bool:
        """
        Register a module class with its capabilities and metadata
        
        Args:
            module_class: The module class to register
            
        Returns:
            True if registration successful, False otherwise
            
        Raises:
            ValueError: If module doesn't implement required interface
        """
        try:
            # Validate module interface
            if not hasattr(module_class, 'get_metadata'):
                raise ValueError(f"Module {module_class.__name__} must implement get_metadata() classmethod")
            
            # Get module metadata
            metadata = module_class.get_metadata()
            if not isinstance(metadata, ModuleMetadata):
                raise ValueError(f"Module {module_class.__name__} get_metadata() must return ModuleMetadata instance")
            
            module_name = metadata.name
            version = metadata.version
            
            # Initialize module entry if needed
            if module_name not in self.modules:
                self.modules[module_name] = {}
                self._dependency_graph[module_name] = set()
            
            # Check for version conflicts
            if str(version) in self.modules[module_name]:
                logger.warning(f"Module {module_name} version {version} already registered, overwriting")
            
            # Store module information
            module_info = {
                'class': module_class,
                'metadata': metadata,
                'capabilities': metadata.capabilities,
                'extension_points': metadata.extension_points,
                'dependencies': metadata.dependencies,
                'description': metadata.description,
                'version': version,
                'registered_at': __import__('time').time()
            }
            
            self.modules[module_name][str(version)] = module_info
            
            # Update latest version tracking
            if module_name not in self._latest_versions or version > self._latest_versions[module_name]:
                self._latest_versions[module_name] = version
            
            # Update capability index
            self._update_capability_index(module_name, metadata.capabilities)
            
            # Update extension point index
            self._update_extension_point_index(module_name, metadata.extension_points)
            
            # Update dependency graph
            self._dependency_graph[module_name] = set(metadata.dependencies)
            
            logger.info(f"Registered module: {module_name} v{version} with capabilities: {[c.value for c in metadata.capabilities]}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register module {module_class.__name__}: {e}")
            return False
        
    def unregister(self, module_name: str, version: Optional[str] = None) -> bool:
        """
        Unregister a module (or specific version) from the registry
        
        Args:
            module_name: Name of the module to unregister
            version: Optional specific version to unregister (unregisters all if None)
            
        Returns:
            True if successfully unregistered, False otherwise
        """
        if module_name not in self.modules:
            logger.warning(f"Module {module_name} not found in registry")
            return False
        
        try:
            if version:
                # Unregister specific version
                if version not in self.modules[module_name]:
                    logger.warning(f"Module {module_name} version {version} not found")
                    return False
                
                del self.modules[module_name][version]
                
                # Update latest version if this was the latest
                if self._latest_versions.get(module_name) == Version(version):
                    remaining_versions = [Version(v) for v in self.modules[module_name].keys()]
                    if remaining_versions:
                        self._latest_versions[module_name] = max(remaining_versions)
                    else:
                        del self._latest_versions[module_name]
                
                # If no versions left, clean up completely
                if not self.modules[module_name]:
                    del self.modules[module_name]
                    self._cleanup_indexes(module_name)
                
            else:
                # Unregister all versions
                del self.modules[module_name]
                self._latest_versions.pop(module_name, None)
                self._cleanup_indexes(module_name)
            
            logger.info(f"Unregistered module: {module_name}" + (f" version {version}" if version else ""))
            return True
            
        except Exception as e:
            logger.error(f"Failed to unregister module {module_name}: {e}")
            return False
    
    def get_module_info(self, module_name: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get information about a registered module
        
        Args:
            module_name: Name of the module
            version: Optional specific version (uses latest if None)
            
        Returns:
            Module information dictionary or None if not found
        """
        if module_name not in self.modules:
            return None
        
        if version:
            return self.modules[module_name].get(version)
        else:
            # Return latest version
            latest_version = self._latest_versions.get(module_name)
            if latest_version:
                return self.modules[module_name].get(str(latest_version))
        
        return None
    
    def get_available_versions(self, module_name: str) -> List[Version]:
        """Get all available versions of a module"""
        if module_name not in self.modules:
            return []
        
        return sorted([Version(v) for v in self.modules[module_name].keys()], reverse=True)
    
    def get_latest_version(self, module_name: str) -> Optional[Version]:
        """Get the latest version of a module"""
        return self._latest_versions.get(module_name)
    
    def find_compatible_version(
        self, 
        module_name: str, 
        version_constraint: Optional[str] = None
    ) -> Optional[Version]:
        """
        Find a compatible version of a module based on version constraint
        
        Args:
            module_name: Name of the module
            version_constraint: Optional version constraint (e.g., ">=1.0.0,<2.0.0")
            
        Returns:
            Compatible version or None if not found
        """
        available_versions = self.get_available_versions(module_name)
        if not available_versions:
            return None
        
        if not version_constraint:
            return available_versions[0]  # Latest version
        
        try:
            from semantic_version import Spec
            spec = Spec(version_constraint)
            
            for version in available_versions:
                if spec.match(version):
                    return version
            
            return None
            
        except Exception as e:
            logger.error(f"Invalid version constraint '{version_constraint}': {e}")
            return available_versions[0]  # Fall back to latest
    
    def get_modules_by_capability(self, capability: ModuleCapability) -> List[str]:
        """
        Find all modules that provide a specific capability
        
        Args:
            capability: The capability to search for
            
        Returns:
            List of module names that provide the capability
        """
        return list(self._capability_index.get(capability, set()))
    
    def get_modules_by_extension_point(self, extension_point: ExtensionPoint) -> List[str]:
        """
        Find all modules that use a specific extension point
        
        Args:
            extension_point: The extension point to search for
            
        Returns:
            List of module names that use the extension point
        """
        return list(self._extension_point_index.get(extension_point, set()))
    
    def get_all_capabilities(self) -> List[ModuleCapability]:
        """Get all registered capabilities"""
        return list(self._capability_index.keys())
    
    def get_all_extension_points(self) -> List[ExtensionPoint]:
        """Get all registered extension points"""
        return list(self._extension_point_index.keys())
    
    def get_all_modules(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Get all registered modules and their versions"""
        return self.modules.copy()
    
    def validate_dependencies(self, module_name: str, version: Optional[str] = None) -> tuple[bool, List[str]]:
        """
        Validate that all dependencies for a module are available
        
        Args:
            module_name: Name of the module to validate
            version: Optional specific version
            
        Returns:
            Tuple of (is_valid, missing_dependencies)
        """
        module_info = self.get_module_info(module_name, version)
        if not module_info:
            return False, [f"Module {module_name}" + (f" version {version}" if version else "") + " not found"]
        
        dependencies = module_info.get('dependencies', [])
        missing = []
        
        for dep in dependencies:
            if dep not in self.modules:
                missing.append(dep)
        
        return len(missing) == 0, missing
    
    def check_version_compatibility(
        self, 
        module_name: str, 
        version: str,
        pipecat_version: Optional[Version] = None
    ) -> bool:
        """
        Check if a module version is compatible with the current environment
        
        Args:
            module_name: Name of the module
            version: Version to check
            pipecat_version: Current Pipecat version
            
        Returns:
            True if compatible, False otherwise
        """
        module_info = self.get_module_info(module_name, version)
        if not module_info:
            return False
        
        metadata = module_info['metadata']
        
        # Check Pipecat version compatibility
        if pipecat_version:
            if metadata.min_pipecat_version and pipecat_version < metadata.min_pipecat_version:
                return False
            if metadata.max_pipecat_version and pipecat_version > metadata.max_pipecat_version:
                return False
        
        return True
    
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
        # Build dependency graph using latest versions
        graph = {}
        for name in module_names:
            info = self.get_module_info(name)  # Uses latest version
            if info:
                graph[name] = info.get('dependencies', [])
            else:
                graph[name] = []
        
        # Topological sort
        visited = set()
        temp_visited = set()
        stack = []
        
        def visit(node):
            if node in temp_visited:
                raise ValueError(f"Circular dependency detected involving: {node}")
            
            if node not in visited:
                temp_visited.add(node)
                
                for dep in graph.get(node, []):
                    if dep in module_names:  # Only consider requested modules
                        visit(dep)
                
                temp_visited.remove(node)
                visited.add(node)
                stack.append(node)
        
        for name in module_names:
            if name not in visited:
                visit(name)
        
        return stack
    
    def detect_conflicts(self) -> List[Dict[str, Any]]:
        """
        Detect potential conflicts between registered modules
        
        Returns:
            List of conflict descriptions
        """
        conflicts = []
        
        # Check for capability conflicts (multiple modules providing same capability)
        for capability, modules in self._capability_index.items():
            if len(modules) > 1:
                conflicts.append({
                    'type': 'capability_conflict',
                    'capability': capability.value,
                    'modules': list(modules),
                    'description': f"Multiple modules provide capability '{capability.value}': {', '.join(modules)}"
                })
        
        # Check for missing dependencies
        for module_name in self.modules:
            is_valid, missing = self.validate_dependencies(module_name)
            if not is_valid:
                conflicts.append({
                    'type': 'missing_dependency',
                    'module': module_name,
                    'missing_dependencies': missing,
                    'description': f"Module '{module_name}' has missing dependencies: {', '.join(missing)}"
                })
        
        return conflicts
    
    def to_dict(self) -> Dict[str, Any]:
        """Export registry state as dictionary"""
        return {
            'modules': {
                name: {
                    version: {
                        'capabilities': [c.value for c in info['capabilities']],
                        'extension_points': [ep.value for ep in info['extension_points']],
                        'dependencies': info['dependencies'],
                        'description': info['description'],
                        'version': str(info['version']),
                        'registered_at': info['registered_at']
                    }
                    for version, info in versions.items()
                }
                for name, versions in self.modules.items()
            },
            'capability_index': {
                cap.value: list(modules)
                for cap, modules in self._capability_index.items()
            },
            'extension_point_index': {
                ep.value: list(modules)
                for ep, modules in self._extension_point_index.items()
            },
            'latest_versions': {
                name: str(version)
                for name, version in self._latest_versions.items()
            }
        }
    
    # Internal helper methods
    
    def _update_capability_index(self, module_name: str, capabilities: List[ModuleCapability]) -> None:
        """Update the capability index for a module"""
        for capability in capabilities:
            if capability not in self._capability_index:
                self._capability_index[capability] = set()
            self._capability_index[capability].add(module_name)
    
    def _update_extension_point_index(self, module_name: str, extension_points: List[ExtensionPoint]) -> None:
        """Update the extension point index for a module"""
        for extension_point in extension_points:
            if extension_point not in self._extension_point_index:
                self._extension_point_index[extension_point] = set()
            self._extension_point_index[extension_point].add(module_name)
    
    def _cleanup_indexes(self, module_name: str) -> None:
        """Clean up indexes when a module is completely removed"""
        # Clean capability index
        for capability, modules in list(self._capability_index.items()):
            modules.discard(module_name)
            if not modules:
                del self._capability_index[capability]
        
        # Clean extension point index
        for extension_point, modules in list(self._extension_point_index.items()):
            modules.discard(module_name)
            if not modules:
                del self._extension_point_index[extension_point]
        
        # Clean dependency graph
        self._dependency_graph.pop(module_name, None)