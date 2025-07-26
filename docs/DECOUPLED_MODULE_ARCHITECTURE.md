# Decoupled Module Architecture for MaestroCat

## Overview

This document proposes a decoupled architecture for the MaestroCat module system, removing tight coupling between the ModuleLoader and the Pipecat pipeline.

## Current Architecture Problems

1. **ModuleLoader inherits from FrameProcessor** but doesn't process frames meaningfully
2. **Circular dependencies** between ModuleLoader, EventEmitter, and Pipeline
3. **No clear integration points** - ModuleLoader is created but not added to pipeline
4. **Limited module capabilities** - Modules can only react to events, not influence pipeline

## Proposed Architecture

### 1. Service-Based Module System

```python
# core/services/module_service.py
class ModuleService:
    """Standalone service for managing modules"""
    
    def __init__(self):
        self.modules: Dict[str, MaestroCatModule] = {}
        self.registry = ModuleRegistry()
        self.context_manager = ContextManager()
        
    async def start(self):
        """Start the module service independently of pipeline"""
        pass
        
    def register_module(self, module_class: Type[MaestroCatModule]):
        """Register a module type with capabilities"""
        self.registry.register(module_class)
```

### 2. Module Registry Pattern

```python
# core/modules/registry.py
class ModuleRegistry:
    """Central registry for module capabilities"""
    
    def register(self, module_class: Type[MaestroCatModule]):
        capabilities = module_class.get_capabilities()
        self.modules[module_class.__name__] = {
            'class': module_class,
            'capabilities': capabilities,
            'hooks': module_class.get_hooks()
        }
```

### 3. Pipeline Extension Points

```python
# core/pipeline/extension_points.py
class ExtensionPoint(Enum):
    PRE_STT = "pre_stt"
    POST_STT = "post_stt"
    PRE_LLM = "pre_llm"
    POST_LLM = "post_llm"
    PRE_TTS = "pre_tts"
    POST_TTS = "post_tts"
    INTERRUPTION = "interruption"

class ExtensionManager:
    """Manages extension points in the pipeline"""
    
    def __init__(self):
        self.hooks: Dict[ExtensionPoint, List[Callable]] = {}
        
    def register_hook(self, point: ExtensionPoint, handler: Callable):
        self.hooks[point].append(handler)
        
    async def execute_hooks(self, point: ExtensionPoint, context: PipelineContext):
        for handler in self.hooks.get(point, []):
            context = await handler(context)
        return context
```

### 4. Context API

```python
# core/context/pipeline_context.py
class PipelineContext:
    """Shared context for pipeline and modules"""
    
    def __init__(self):
        self.conversation_history: List[Message] = []
        self.current_transcription: Optional[str] = None
        self.llm_response: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
        self.module_data: Dict[str, Any] = {}
        
    def get_module_data(self, module_name: str) -> Any:
        return self.module_data.get(module_name)
        
    def set_module_data(self, module_name: str, data: Any):
        self.module_data[module_name] = data
```

### 5. Decoupled Module Interface

```python
# core/modules/base.py
class MaestroCatModule(ABC):
    """Base module without pipeline dependencies"""
    
    @classmethod
    @abstractmethod
    def get_capabilities(cls) -> List[str]:
        """Declare module capabilities"""
        pass
        
    @classmethod
    @abstractmethod
    def get_hooks(cls) -> Dict[ExtensionPoint, str]:
        """Declare which extension points this module uses"""
        pass
        
    async def handle_extension(self, 
                             point: ExtensionPoint, 
                             context: PipelineContext) -> PipelineContext:
        """Handle pipeline extension point"""
        pass
```

## Implementation Examples

### 1. Memory Module (Decoupled)

```python
class MemoryModule(MaestroCatModule):
    @classmethod
    def get_capabilities(cls):
        return ["conversation_memory", "context_injection"]
        
    @classmethod
    def get_hooks(cls):
        return {
            ExtensionPoint.POST_STT: "save_user_message",
            ExtensionPoint.POST_LLM: "save_assistant_message",
            ExtensionPoint.PRE_LLM: "inject_context"
        }
        
    async def handle_extension(self, point: ExtensionPoint, context: PipelineContext):
        if point == ExtensionPoint.POST_STT:
            self.conversation_memory.add_user_message(context.current_transcription)
        elif point == ExtensionPoint.PRE_LLM:
            context.metadata['memory_context'] = self.get_relevant_memories()
        return context
```

### 2. Pipeline Integration

```python
class MaestroCatPipeline:
    def __init__(self, module_service: ModuleService):
        self.module_service = module_service
        self.extension_manager = ExtensionManager()
        self.context = PipelineContext()
        
        # Register module hooks
        for module in module_service.get_active_modules():
            for point, handler_name in module.get_hooks().items():
                handler = partial(module.handle_extension, point)
                self.extension_manager.register_hook(point, handler)
    
    async def process_audio(self, audio_frame):
        # Pre-STT hooks
        self.context = await self.extension_manager.execute_hooks(
            ExtensionPoint.PRE_STT, self.context
        )
        
        # STT processing
        transcription = await self.stt_service.process(audio_frame)
        self.context.current_transcription = transcription
        
        # Post-STT hooks
        self.context = await self.extension_manager.execute_hooks(
            ExtensionPoint.POST_STT, self.context
        )
        
        # Continue pipeline...
```

## Benefits of Decoupled Architecture

1. **Independent Module Service** - Modules run separately from pipeline
2. **Clear Extension Points** - Modules know exactly where they can hook in
3. **Shared Context** - Clean data passing without frame manipulation
4. **No Circular Dependencies** - Clear service boundaries
5. **Better Testability** - Modules can be tested in isolation
6. **Dynamic Loading** - Modules can be added/removed without pipeline restart

## Migration Path

1. **Phase 1**: Implement ModuleService alongside existing ModuleLoader
2. **Phase 2**: Add extension points to pipeline processors
3. **Phase 3**: Migrate existing modules to new interface
4. **Phase 4**: Remove old ModuleLoader and EventEmitter dependencies
5. **Phase 5**: Optimize and add new capabilities

## Example Usage

```python
# Initialize services
module_service = ModuleService()
module_service.register_module(MemoryModule)
module_service.register_module(VoiceRecognitionModule)

# Create pipeline with module integration
pipeline = MaestroCatPipeline(module_service)

# Modules automatically hook into pipeline at defined extension points
await pipeline.run()
```

This architecture provides clean separation of concerns while maintaining the flexibility to extend pipeline behavior through modules.