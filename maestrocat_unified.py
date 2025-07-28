#!/usr/bin/env python3
"""
MaestroCat Universal Launcher (New Platform Abstraction System)

This is the new unified launcher that uses the platform abstraction system
to eliminate code duplication and provide a consistent experience across
all supported platforms.

Features:
- Automatic platform detection and optimization
- Unified configuration with platform-specific sections
- Intelligent service selection and fallbacks
- Comprehensive health checking and setup validation
- Clean command-line interface
- Backward compatibility with existing configurations
"""

import asyncio
import argparse
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent))

from core.platform import (
    MaestroCatAgent, 
    PlatformDetector, 
    ServiceFactory,
    PlatformType
)
from core.platform.config import UnifiedMaestroCatConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MaestroCatLauncher:
    """
    Unified launcher for MaestroCat that handles platform detection,
    service setup, and agent lifecycle management.
    """
    
    def __init__(self):
        self.agent = None
        self.platform_info = None
        self._shutdown_event = None
    
    async def check_platform_compatibility(self, 
                                         platform_type: Optional[PlatformType] = None) -> bool:
        """
        Check if the current platform is compatible with MaestroCat.
        
        Args:
            platform_type: Force specific platform type for checking
            
        Returns:
            True if platform is compatible, False otherwise
        """
        logger.info("🔍 Analyzing platform compatibility...")
        
        # Get platform information
        self.platform_info = PlatformDetector.detect_full_platform_info()
        
        # Override platform type if specified
        if platform_type:
            logger.info(f"🎯 Using forced platform type: {platform_type.value}")
            detected_platform = platform_type
        else:
            detected_platform = PlatformDetector.auto_select_strategy_type(self.platform_info)
        
        # Print platform information
        print(f"\n🖥️  Platform Detection Results:")
        print(f"   System: {self.platform_info.description}")
        print(f"   Selected Strategy: {detected_platform.value}")
        print(f"   Capabilities:")
        print(f"     • GPU Available: {self.platform_info.capabilities.has_gpu}")
        print(f"     • Metal Support: {self.platform_info.capabilities.supports_metal}")
        print(f"     • MLX Support: {self.platform_info.capabilities.supports_mlx}")
        print(f"     • Docker Available: {self.platform_info.capabilities.docker_available}")
        print(f"     • Native Services: {', '.join(self.platform_info.capabilities.native_services) or 'None'}")
        
        # Get recommendations
        recommendations = ServiceFactory.get_strategy_recommendations({})
        print(f"\n💡 Platform Recommendations:")
        print(f"   Recommended Strategy: {recommendations['recommended_strategy']}")
        for reason in recommendations['reasoning']:
            print(f"   • {reason}")
        
        if recommendations['performance_notes']:
            print(f"   Performance Notes:")
            for note in recommendations['performance_notes']:
                print(f"   • {note}")
        
        # Check for potential issues
        issues = []
        
        if detected_platform == PlatformType.DOCKER:
            if not self.platform_info.capabilities.docker_available:
                issues.append("Docker strategy selected but Docker is not available")
        
        elif detected_platform == PlatformType.MACOS_NATIVE:
            if "ollama" not in self.platform_info.capabilities.native_services:
                issues.append("macOS native strategy selected but Ollama is not available")
        
        if issues:
            print(f"\n⚠️  Compatibility Issues:")
            for issue in issues:
                print(f"   • {issue}")
            return False
        
        print(f"\n✅ Platform is compatible with MaestroCat!")
        return True
    
    async def setup_services(self, config: UnifiedMaestroCatConfig) -> bool:
        """
        Set up platform services based on configuration.
        
        Args:
            config: Unified configuration
            
        Returns:
            True if setup successful, False otherwise
        """
        logger.info("🔧 Setting up platform services...")
        
        # Create strategy
        strategy = ServiceFactory.auto_create_strategy(config)
        
        # Check dependencies
        logger.info("📋 Checking platform dependencies...")
        deps_ok, missing_deps = await strategy.check_dependencies()
        
        if not deps_ok:
            print(f"\n❌ Missing Dependencies:")
            for dep in missing_deps:
                print(f"   • {dep}")
            
            # Show setup instructions
            platform_type = strategy.platform_info.platform_type
            print(f"\n🔧 Setup Instructions for {platform_type.value}:")
            
            if platform_type == PlatformType.MACOS_NATIVE:
                print("   # Install native dependencies")
                print("   brew install ollama ffmpeg")
                print("   pip install 'pipecat-ai[mlx-whisper]'")
                print("")
                print("   # Start services")
                print("   ollama serve &")
                print("   ollama pull llama3.2:3b")
            
            elif platform_type == PlatformType.DOCKER:
                print("   # Install Docker")
                print("   # Visit: https://docker.com")
                print("")
                print("   # Start Docker daemon")
                print("   sudo systemctl start docker  # Linux")
                print("   # or start Docker Desktop")
            
            return False
        
        print(f"✅ All dependencies are available")
        
        # Set up services
        logger.info("🚀 Starting platform services...")
        services_ok = await strategy.setup_services()
        
        if not services_ok:
            print(f"❌ Failed to start platform services")
            return False
        
        print(f"✅ Platform services are ready")
        
        # Clean up strategy
        await strategy.cleanup()
        
        return True
    
    async def run_agent(self, 
                       config_file: Optional[str] = None,
                       platform_type: Optional[PlatformType] = None,
                       host: str = "0.0.0.0",
                       port: int = 8765) -> int:
        """
        Run the MaestroCat agent.
        
        Args:
            config_file: Path to configuration file
            platform_type: Force specific platform type
            host: Host to bind to
            port: Port to bind to
            
        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            # Load configuration
            if config_file:
                config = UnifiedMaestroCatConfig.from_file(config_file, platform_type)
            else:
                config = UnifiedMaestroCatConfig.auto_load(platform_type=platform_type)
            
            logger.info(f"📄 Loaded configuration: {config}")
            
            # Create and run agent
            self.agent = MaestroCatAgent(config=config, platform_override=platform_type)
            
            logger.info("🎭 Starting MaestroCat Universal Agent...")
            
            # Run agent - it handles its own shutdown
            await self.agent.run(host=host, websocket_port=port)
            
            return 0
            
        except KeyboardInterrupt:
            logger.info("👋 Shutting down MaestroCat...")
            return 0
        except Exception as e:
            logger.error(f"❌ Error running MaestroCat: {e}")
            return 1
        finally:
            if self.agent:
                logger.info("🧹 Cleaning up MaestroCat Agent...")
                await self.agent.cleanup()
                logger.info("✅ Cleanup complete")
    
    def print_platform_status(self):
        """Print detailed platform status information"""
        if not self.platform_info:
            self.platform_info = PlatformDetector.detect_full_platform_info()
        
        print(f"\n🎭 MaestroCat Platform Status")
        print(f"=" * 50)
        print(f"Platform: {self.platform_info.description}")
        print(f"Type: {self.platform_info.platform_type.value}")
        print(f"")
        print(f"Capabilities:")
        print(f"  GPU Available: {self.platform_info.capabilities.has_gpu}")
        print(f"  Metal Support: {self.platform_info.capabilities.supports_metal}")
        print(f"  MLX Support: {self.platform_info.capabilities.supports_mlx}")
        print(f"  Docker Available: {self.platform_info.capabilities.docker_available}")
        print(f"  Native Services: {', '.join(self.platform_info.capabilities.native_services) or 'None'}")
        print(f"")
        print(f"Recommended Models:")
        for service, model in self.platform_info.recommended_models.items():
            print(f"  {service.upper()}: {model}")
        print(f"=" * 50)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="MaestroCat Universal Launcher - Platform-agnostic voice AI agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                                    # Auto-detect platform and run
    %(prog)s --config config/custom.yaml       # Use custom configuration
    %(prog)s --platform macos_native           # Force macOS native platform
    %(prog)s --check                           # Check platform compatibility only
    %(prog)s --status                          # Show platform status
    %(prog)s --setup                           # Set up services only

Platform Types:
    docker          Docker-based services (Linux, Windows, WSL)
    macos_native    macOS native services (Whisper.cpp + Ollama + macOS TTS)
    wsl             Windows Subsystem for Linux (extends Docker)
    windows         Windows (extends Docker)

Configuration:
    • Unified config:  config/maestrocat_unified.yaml
    • Legacy configs:  config/maestrocat.yaml, config/maestrocat_macos.yaml
    • Auto-detection: Automatically selects best config for platform
        """
    )
    
    # Configuration options
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="Path to configuration file (auto-detects if not specified)"
    )
    
    parser.add_argument(
        "--platform", "-p",
        choices=["docker", "macos_native", "wsl", "windows"],
        help="Force specific platform type (overrides auto-detection)"
    )
    
    # Service options
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind WebSocket server to (default: 0.0.0.0)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for WebSocket server (default: 8765)"
    )
    
    # Utility commands
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check platform compatibility and exit"
    )
    
    parser.add_argument(
        "--status",
        action="store_true", 
        help="Show platform status and exit"
    )
    
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Set up platform services only (don't run agent)"
    )
    
    # Debug options
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Parse platform type
    platform_type = None
    if args.platform:
        platform_type = PlatformType(args.platform)
    
    # Create launcher
    launcher = MaestroCatLauncher()
    
    async def run():
        # Handle utility commands
        if args.status:
            launcher.print_platform_status()
            return 0
        
        if args.check:
            compatible = await launcher.check_platform_compatibility(platform_type)
            return 0 if compatible else 1
        
        if args.setup:
            # Load config for setup
            if args.config:
                config = UnifiedMaestroCatConfig.from_file(args.config, platform_type)
            else:
                config = UnifiedMaestroCatConfig.auto_load(platform_type=platform_type)
            
            success = await launcher.setup_services(config)
            return 0 if success else 1
        
        # Run the agent
        return await launcher.run_agent(
            config_file=args.config,
            platform_type=platform_type,
            host=args.host,
            port=args.port
        )
    
    # Run the launcher
    try:
        exit_code = asyncio.run(run())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()