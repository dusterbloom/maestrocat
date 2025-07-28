"""
Unified MaestroCat Agent

Provides a single, unified agent implementation that uses platform strategies
to eliminate code duplication between Docker and macOS implementations.
This agent automatically adapts to the current platform while maintaining
consistent functionality and interfaces.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from fastapi import FastAPI, WebSocket
import uvicorn

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

from .strategy import PlatformStrategy, PlatformType
from .factory import ServiceFactory
from ..processors import (
    InterruptionHandler,
    MetricsCollector,
    EventEmitter,
    ModuleLoader
)
from .config import UnifiedMaestroCatConfig
from ..modules import VoiceRecognitionModule, MemoryModule
from ..apps.debug_ui import DebugUIServer

logger = logging.getLogger(__name__)


class MaestroCatAgent:
    """
    Unified MaestroCat agent that works across all supported platforms.
    
    This agent replaces the separate LocalMaestroCatAgent and MacOSMaestroCatAgent
    classes, providing a single implementation that automatically adapts to the
    current platform using platform strategies.
    
    Features:
    - Automatic platform detection and optimization
    - Unified configuration with platform-specific sections
    - Consistent API across all platforms
    - Built-in service health monitoring
    - Extensible module system
    - Debug UI integration
    """
    
    def __init__(self, 
                 config_file: Optional[str] = None,
                 platform_override: Optional[PlatformType] = None,
                 config: Optional[UnifiedMaestroCatConfig] = None):
        """
        Initialize the unified MaestroCat agent.
        
        Args:
            config_file: Path to configuration file (optional if config provided)
            platform_override: Force specific platform type (optional)
            config: Pre-loaded configuration object (optional)
        """
        # Load configuration
        if config:
            self.config = config
        elif config_file:
            self.config = UnifiedMaestroCatConfig.from_file(config_file, platform_override)
        else:
            # Auto-load the best available configuration
            self.config = UnifiedMaestroCatConfig.auto_load(platform_type=platform_override)
        
        # Create platform strategy
        self.strategy = ServiceFactory.auto_create_strategy(self.config, platform_override)
        
        # Core components
        self.event_emitter = None
        self.metrics_collector = None
        self.module_loader = None
        self.debug_ui = None
        self.interruption_handler = None
        
        # Services (created by strategy)
        self.stt = None
        self.llm = None
        self.tts = None
        
        # Transport parameters
        self.transport_params = None
        
        # State tracking
        self._setup_complete = False
        self._services_ready = False
    
    @property
    def platform_info(self):
        """Get information about the current platform"""
        return self.strategy.platform_info
    
    async def setup(self) -> bool:
        """
        Set up the agent with platform-optimized services.
        
        Returns:
            True if setup successful, False otherwise
        """
        if self._setup_complete:
            return True
        
        logger.info(f"Setting up MaestroCat Agent")
        logger.info(f"Platform: {self.platform_info.description}")
        
        try:
            # Check platform dependencies
            deps_ok, missing_deps = await self.strategy.check_dependencies()
            if not deps_ok:
                logger.error("Missing platform dependencies:")
                for dep in missing_deps:
                    logger.error(f"  - {dep}")
                return False
            
            # Set up platform services
            services_ok = await self.strategy.setup_services()
            if not services_ok:
                logger.error("Failed to set up platform services")
                return False
            
            # Create core processors
            await self._setup_core_processors()
            
            # Create platform-optimized services
            await self._create_services()
            
            # Create transport parameters
            self.transport_params = self.strategy.create_transport_params()
            
            # Apply platform optimizations
            optimizations = await self.strategy.apply_platform_optimizations()
            if optimizations:
                logger.info(f"Applied platform optimizations: {optimizations}")
            
            # Load modules
            await self._load_modules()
            
            self._setup_complete = True
            self._services_ready = True
            
            logger.info("✅ MaestroCat Agent setup complete")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to set up MaestroCat Agent: {e}")
            return False
    
    async def _setup_core_processors(self):
        """Set up core processors (event system, metrics, etc.)"""
        # Create event system
        self.event_emitter = EventEmitter(
            buffer_size=1000, 
            emit_as_frames=False
        )
        
        # Create metrics collector
        self.metrics_collector = MetricsCollector(
            emit_interval=5.0,
            event_emitter=self.event_emitter
        )
        
        # Create debug UI
        debug_port = 8080
        if hasattr(self.config, 'development'):
            debug_port = getattr(self.config.development, 'debug_port', 8080)
        
        self.debug_ui = DebugUIServer(port=debug_port)
        self.debug_ui.attach_event_emitter(self.event_emitter)
        self.debug_ui.attach_config(self.config)
        
        # Create module loader
        self.module_loader = ModuleLoader(self.event_emitter)
        
        # Create interruption handler
        self.interruption_handler = InterruptionHandler(
            threshold=self.config.interruption.threshold,
            ack_delay=self.config.interruption.ack_delay
        )
    
    async def _create_services(self):
        """Create platform-specific services using the strategy"""
        logger.info("Creating platform-optimized services...")
        
        # Create services through platform strategy
        self.stt = await self.strategy.create_stt_service(self.event_emitter)
        self.llm = await self.strategy.create_llm_service(self.event_emitter)
        self.tts = await self.strategy.create_tts_service(self.event_emitter)
        
        logger.info(f"✅ STT: {type(self.stt).__name__}")
        logger.info(f"✅ LLM: {type(self.llm).__name__}")
        logger.info(f"✅ TTS: {type(self.tts).__name__}")
    
    async def _load_modules(self):
        """Load configured modules"""
        # Load voice recognition module
        if self.config.modules.get("voice_recognition", {}).get("enabled", False):
            await self.module_loader.load_module(
                VoiceRecognitionModule,
                self.config.modules["voice_recognition"]
            )
            logger.info("✅ Voice recognition module loaded")
        
        # Load memory module
        if self.config.modules.get("memory", {}).get("enabled", False):
            await self.module_loader.load_module(
                MemoryModule,
                self.config.modules["memory"]
            )
            logger.info("✅ Memory module loaded")
    
    async def create_pipeline(self, websocket: WebSocket) -> tuple[Pipeline, Any]:
        """
        Create a pipeline for the given WebSocket connection.
        
        Args:
            websocket: The WebSocket connection
            
        Returns:
            Tuple of (pipeline, transport)
        """
        if not self._services_ready:
            raise RuntimeError("Agent not set up. Call setup() first.")
        
        # Import transport class here to avoid circular imports
        from pipecat.transports.network.fastapi_websocket import FastAPIWebsocketTransport
        
        # Create transport for this WebSocket
        transport = FastAPIWebsocketTransport(websocket, self.transport_params)
        
        # Create LLM context with system prompt
        system_prompt = self.strategy.get_system_prompt()
        
        context = OpenAILLMContext(messages=[
            {
                "role": "system",
                "content": system_prompt
            }
        ])
        
        # Create context aggregators using the LLM service
        context_aggregator = self.llm.create_context_aggregator(context)
        
        # Build the pipeline
        pipeline = Pipeline([
            # Input
            transport.input(),
            
            # STT
            self.stt,
            
            # User context aggregation (TranscriptionFrame → LLM trigger)
            context_aggregator.user(),
            
            # LLM
            self.llm,
            
            # TTS
            self.tts,
            
            # Output
            transport.output(),
            
            # Assistant context aggregation (LLM response handling)
            context_aggregator.assistant(),
        ])
        
        return pipeline, transport
    
    async def handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection"""
        await websocket.accept()
        
        pipeline, transport = await self.create_pipeline(websocket)
        
        # Create pipeline task with platform-appropriate parameters
        task_params = PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True
        )
        
        task = PipelineTask(pipeline, params=task_params)
        runner = PipelineRunner()
        
        logger.info(f"WebSocket connected: {websocket.client}")
        
        try:
            await runner.run(task)
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
        finally:
            logger.info(f"WebSocket disconnected: {websocket.client}")
    
    def create_app(self) -> FastAPI:
        """Create FastAPI application with unified endpoints"""
        app = FastAPI(
            title="MaestroCat Universal Agent",
            description=f"Platform: {self.platform_info.description}",
            version="2.0.0"
        )
        
        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.handle_websocket(websocket)
        
        @app.get("/health")
        async def health_check():
            """Health check endpoint with platform information"""
            strategy_health = self.strategy.get_health_info()
            
            return {
                "status": "healthy" if self._services_ready else "initializing",
                "platform": self.platform_info.platform_type.value,
                "description": self.platform_info.description,
                "services": {
                    "stt": type(self.stt).__name__ if self.stt else None,
                    "llm": type(self.llm).__name__ if self.llm else None,
                    "tts": type(self.tts).__name__ if self.tts else None
                },
                "capabilities": {
                    "has_gpu": self.platform_info.capabilities.has_gpu,
                    "supports_metal": self.platform_info.capabilities.supports_metal,
                    "supports_mlx": self.platform_info.capabilities.supports_mlx,
                    "docker_available": self.platform_info.capabilities.docker_available,
                    "native_services": self.platform_info.capabilities.native_services
                },
                "strategy_health": strategy_health
            }
        
        @app.get("/platform")
        async def platform_info():
            """Get detailed platform information"""
            return {
                "platform_type": self.platform_info.platform_type.value,
                "description": self.platform_info.description,
                "capabilities": self.platform_info.capabilities.__dict__,
                "recommended_models": self.platform_info.recommended_models,
                "service_specs": self.strategy.service_specs.__dict__,
                "debug_info": self.strategy.get_debug_info()
            }
        
        @app.get("/")
        async def root():
            """Root endpoint with platform information"""
            return {
                "name": "MaestroCat Universal Agent",
                "version": "2.0.0",
                "platform": self.platform_info.description,
                "endpoints": {
                    "websocket": "/ws",
                    "health": "/health",
                    "platform": "/platform"
                }
            }
        
        return app
    
    async def run(self, host: str = "0.0.0.0", websocket_port: int = 8765):
        """
        Run the agent with both WebSocket and debug UI servers.
        
        Args:
            host: Host to bind to
            websocket_port: Port for WebSocket server
        """
        # Set up the agent
        if not await self.setup():
            logger.error("Failed to set up agent")
            return
        
        app = self.create_app()
        
        # Get debug port from config if available
        debug_port = 8080
        if hasattr(self.config, 'development'):
            debug_port = getattr(self.config.development, 'debug_port', 8080)
            websocket_port = getattr(self.config.development, 'websocket_port', websocket_port)
        
        # Log startup information
        self._log_startup_info(websocket_port, debug_port)
        
        # Configure WebSocket server
        websocket_config = uvicorn.Config(
            app, 
            host=host, 
            port=websocket_port, 
            log_level="info"
        )
        websocket_server = uvicorn.Server(websocket_config)
        
        # Run both servers concurrently
        try:
            await asyncio.gather(
                self.debug_ui.start(),  # Debug UI
                websocket_server.serve()  # WebSocket server
            )
        except KeyboardInterrupt:
            logger.info("Shutting down MaestroCat Agent...")
        except Exception as e:
            logger.error(f"Error running agent: {e}")
        finally:
            await self.cleanup()
    
    def _log_startup_info(self, websocket_port: int, debug_port: int):
        """Log detailed startup information"""
        logger.info("🎭 MaestroCat Universal Agent Started!")
        logger.info("=" * 60)
        logger.info(f"🖥️  Platform: {self.platform_info.description}")
        
        if self.platform_info.capabilities.supports_mlx:
            logger.info("⚡ Apple Silicon MLX acceleration enabled")
        elif self.platform_info.capabilities.has_gpu:
            logger.info("🚀 GPU acceleration enabled")
        
        logger.info(f"🔊 WebSocket server: ws://localhost:{websocket_port}/ws")  
        logger.info(f"🐛 Debug UI: http://localhost:{debug_port}")
        logger.info(f"❤️  Health check: http://localhost:{websocket_port}/health")
        logger.info(f"🌐 Platform info: http://localhost:{websocket_port}/platform")
        logger.info("")
        logger.info(f"🎤 STT: {type(self.stt).__name__}")
        logger.info(f"🧠 LLM: {self.config.llm.model}")
        logger.info(f"🗣️  TTS: {type(self.tts).__name__}")
        
        # Show platform-specific service info
        strategy_health = self.strategy.get_health_info()
        if "service_urls" in strategy_health:
            logger.info("")
            logger.info("Service URLs:")
            for service, url in strategy_health["service_urls"].items():
                logger.info(f"  {service}: {url}")
        
        logger.info("=" * 60)
        logger.info("")
        logger.info("🚀 Ready for connections!")
    
    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up MaestroCat Agent...")
        
        try:
            # Clean up platform-specific resources
            await self.strategy.cleanup()
            
            # Clean up debug UI
            if self.debug_ui:
                # Debug UI cleanup is handled by the server itself
                pass
            
            logger.info("✅ Cleanup complete")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status"""
        return {
            "setup_complete": self._setup_complete,
            "services_ready": self._services_ready,
            "platform": self.platform_info.platform_type.value,
            "platform_description": self.platform_info.description,
            "services": {
                "stt": type(self.stt).__name__ if self.stt else None,
                "llm": type(self.llm).__name__ if self.llm else None,
                "tts": type(self.tts).__name__ if self.tts else None,
            },
            "strategy_health": self.strategy.get_health_info() if self.strategy else None
        }