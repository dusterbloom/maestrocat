# core/modules/interface.py
"""
New module interface definitions for MaestroCat decoupled architecture
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Type, Set, Union
from enum import Enum
import logging
from dataclasses import dataclass
from semantic_version import Version

logger = logging.getLogger(__name__)


class ExtensionPoint(Enum):
    """Pipeline extension points where modules can hook in"""
    # Audio processing
    PRE_STT = "pre_stt"
    POST_STT = "post_stt"
    
    # LLM processing
    PRE_LLM = "pre_llm"
    POST_LLM = "post_llm"
    
    # TTS processing
    PRE_TTS = "pre_tts"
    POST_TTS = "post_tts"
    
    # Conversation flow
    CONVERSATION_START = "conversation_start"
    CONVERSATION_END = "conversation_end"
    
    # Interruption handling
    INTERRUPTION_DETECTED = "interruption_detected"
    INTERRUPTION_HANDLED = "interruption_handled"
    
    # Frame processing
    FRAME_RECEIVED = "frame_received"
    FRAME_SENT = "frame_sent"
    
    # Error handling
    ERROR_OCCURRED = "error_occurred"


class ModuleCapability(Enum):
    """Standard module capabilities"""
    # Memory and context
    CONVERSATION_MEMORY = "conversation_memory"
    CONTEXT_INJECTION = "context_injection"
    USER_PROFILING = "user_profiling"
    
    # Audio and voice
    VOICE_RECOGNITION = "voice_recognition"
    AUDIO_PROCESSING = "audio_processing"
    EMOTION_DETECTION = "emotion_detection"
    
    # Intelligence and analysis
    INTENT_RECOGNITION = "intent_recognition"
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    LANGUAGE_DETECTION = "language_detection"
    
    # Pipeline control
    INTERRUPTION_HANDLING = "interruption_handling"
    FLOW_CONTROL = "flow_control"
    CUSTOM_COMMANDS = "custom_commands"
    
    # Monitoring and debugging
    METRICS_COLLECTION = "metrics_collection"
    PERFORMANCE_MONITORING = "performance_monitoring"
    DEBUG_LOGGING = "debug_logging"
    
    # External integrations
    API_INTEGRATION = "api_integration"
    DATABASE_STORAGE = "database_storage"
    FILE_IO = "file_io"


@dataclass
class ModuleMetadata:
    """Module metadata and requirements"""
    name: str
    version: Version
    description: str
    author: str
    capabilities: List[ModuleCapability]
    dependencies: List[str] = None
    extension_points: List[ExtensionPoint] = None
    config_schema: Dict[str, Any] = None
    min_pipecat_version: Optional[Version] = None
    max_pipecat_version: Optional[Version] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.extension_points is None:
            self.extension_points = []
        if self.config_schema is None:
            self.config_schema = {}


class ModuleLifecycleState(Enum):
    """Module lifecycle states"""
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ModuleContext:
    """Context passed to modules during operations"""
    module_name: str
    config: Dict[str, Any]
    pipeline_context: 'PipelineContext'
    shared_data: Dict[str, Any]
    logger: logging.Logger
    
    def get_dependency(self, dependency_name: str) -> 'MaestroCatModule':
        """Get a dependency module instance"""
        from .service import ModuleService
        return ModuleService.get_instance().get_module(dependency_name)


class MaestroCatModule(ABC):
    """
    New decoupled base class for MaestroCat modules.
    
    This interface provides:
    - Clear capability declaration
    - Extension point registration
    - Lifecycle management
    - Dependency injection
    - Configuration validation
    """
    
    def __init__(self, context: ModuleContext):
        self.context = context
        self.name = context.module_name
        self.config = context.config
        self.logger = context.logger
        self.state = ModuleLifecycleState.LOADED
        self._dependencies: Dict[str, 'MaestroCatModule'] = {}
        
    @classmethod
    @abstractmethod
    def get_metadata(cls) -> ModuleMetadata:
        """
        Return module metadata including capabilities and requirements.
        
        This method must be implemented by all modules to declare:
        - What capabilities they provide
        - What extension points they use
        - What dependencies they require
        - Version compatibility requirements
        """
        pass
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the module with its configuration.
        
        Returns:
            True if initialization succeeded, False otherwise
        """
        pass
    
    @abstractmethod
    async def start(self) -> bool:
        """
        Start the module and make it ready for operation.
        
        Returns:
            True if start succeeded, False otherwise
        """
        pass
    
    @abstractmethod
    async def stop(self) -> bool:
        """
        Stop the module and cleanup resources.
        
        Returns:
            True if stop succeeded, False otherwise
        """
        pass
    
    async def handle_extension_point(
        self, 
        point: ExtensionPoint, 
        context: 'PipelineContext'
    ) -> 'PipelineContext':
        """
        Handle a pipeline extension point.
        
        Args:
            point: The extension point being executed
            context: The current pipeline context
            
        Returns:
            Modified pipeline context
        """
        # Default implementation does nothing
        return context
    
    async def handle_event(self, event_type: str, data: Any) -> None:
        """
        Handle custom events from other modules or the pipeline.
        
        Args:
            event_type: Type of event
            data: Event data
        """
        # Default implementation does nothing
        pass
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate module configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        # Default implementation accepts any config
        return []
    
    def get_dependency(self, name: str) -> Optional['MaestroCatModule']:
        """Get a dependency module"""
        return self._dependencies.get(name)
    
    def set_dependency(self, name: str, module: 'MaestroCatModule') -> None:
        """Set a dependency module (used by dependency injection)"""
        self._dependencies[name] = module
    
    def get_state(self) -> ModuleLifecycleState:
        """Get current module state"""
        return self.state
    
    def _set_state(self, state: ModuleLifecycleState) -> None:
        """Set module state (internal use only)"""
        old_state = self.state
        self.state = state
        self.logger.debug(f"Module {self.name} state changed: {old_state} -> {state}")


class ModuleInterface(ABC):
    """
    Interface for module capability contracts.
    
    Modules can implement specific interfaces to provide standardized
    capabilities that other modules can depend on.
    """
    
    @abstractmethod
    def get_interface_version(self) -> Version:
        """Return the version of this interface implementation"""
        pass


class ConversationMemoryInterface(ModuleInterface):
    """Interface for conversation memory capabilities"""
    
    @abstractmethod
    async def add_user_message(self, message: str, metadata: Dict[str, Any] = None) -> None:
        """Add a user message to memory"""
        pass
    
    @abstractmethod
    async def add_assistant_message(self, message: str, metadata: Dict[str, Any] = None) -> None:
        """Add an assistant message to memory"""
        pass
    
    @abstractmethod
    async def get_conversation_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent conversation history"""
        pass
    
    @abstractmethod
    async def search_memory(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search through conversation memory"""
        pass


class VoiceRecognitionInterface(ModuleInterface):
    """Interface for voice recognition capabilities"""
    
    @abstractmethod
    async def identify_speaker(self, audio_data: bytes) -> Optional[str]:
        """Identify speaker from audio data"""
        pass
    
    @abstractmethod
    async def register_voice(self, speaker_id: str, audio_samples: List[bytes]) -> bool:
        """Register a new voice profile"""
        pass
    
    @abstractmethod
    async def get_known_speakers(self) -> List[str]:
        """Get list of known speakers"""
        pass


class ContextInjectionInterface(ModuleInterface):
    """Interface for context injection capabilities"""
    
    @abstractmethod
    async def inject_context(self, context: 'PipelineContext') -> 'PipelineContext':
        """Inject additional context into the pipeline"""
        pass
    
    @abstractmethod
    async def get_relevant_context(self, query: str) -> Dict[str, Any]:
        """Get context relevant to a query"""
        pass


# Registry for interface implementations
INTERFACE_REGISTRY: Dict[str, Type[ModuleInterface]] = {
    'conversation_memory': ConversationMemoryInterface,
    'voice_recognition': VoiceRecognitionInterface,
    'context_injection': ContextInjectionInterface,
}


def register_interface(name: str, interface_class: Type[ModuleInterface]) -> None:
    """Register a new module interface"""
    INTERFACE_REGISTRY[name] = interface_class


def get_interface(name: str) -> Optional[Type[ModuleInterface]]:
    """Get an interface class by name"""
    return INTERFACE_REGISTRY.get(name)