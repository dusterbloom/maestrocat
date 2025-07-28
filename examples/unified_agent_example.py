#!/usr/bin/env python3
"""
MaestroCat Unified Agent Example

This example demonstrates how to use the new unified platform abstraction system.
It shows automatic platform detection, configuration loading, and agent initialization
that works across all supported platforms without code changes.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from core.platform import (
    MaestroCatAgent,
    PlatformDetector, 
    ServiceFactory,
    PlatformType
)
from core.platform.config import UnifiedMaestroCatConfig
from core.platform.migration import ConfigMigrator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def example_basic_usage():
    """Example 1: Basic usage with automatic platform detection"""
    print("\n" + "="*60)
    print("Example 1: Basic Unified Agent Usage")
    print("="*60)
    
    # Create agent with automatic platform detection
    agent = MaestroCatAgent()
    
    # Get platform information
    platform_info = agent.platform_info
    print(f"🖥️  Detected Platform: {platform_info.description}")
    print(f"📋 Capabilities:")
    print(f"   • GPU: {platform_info.capabilities.has_gpu}")
    print(f"   • Metal: {platform_info.capabilities.supports_metal}")
    print(f"   • MLX: {platform_info.capabilities.supports_mlx}")
    print(f"   • Docker: {platform_info.capabilities.docker_available}")
    
    # Setup agent (this will check dependencies and configure services)
    print(f"\n🔧 Setting up agent...")
    setup_success = await agent.setup()
    
    if setup_success:
        print(f"✅ Agent setup successful!")
        print(f"🎤 STT Service: {type(agent.stt).__name__}")
        print(f"🧠 LLM Service: {type(agent.llm).__name__}")
        print(f"🗣️  TTS Service: {type(agent.tts).__name__}")
        
        # Get agent status
        status = agent.get_status()
        print(f"\n📊 Agent Status:")
        print(f"   • Setup Complete: {status['setup_complete']}")
        print(f"   • Services Ready: {status['services_ready']}")
        print(f"   • Platform: {status['platform']}")
        
    else:
        print(f"❌ Agent setup failed!")
    
    # Cleanup
    await agent.cleanup()


async def example_platform_detection():
    """Example 2: Detailed platform detection and recommendations"""
    print("\n" + "="*60)
    print("Example 2: Platform Detection and Recommendations")
    print("="*60)
    
    # Get detailed platform information
    platform_info = PlatformDetector.detect_full_platform_info()
    
    print(f"🔍 Platform Detection Results:")
    print(f"   Type: {platform_info.platform_type.value}")
    print(f"   Description: {platform_info.description}")
    print(f"   Recommended Models:")
    for service, model in platform_info.recommended_models.items():
        print(f"     {service.upper()}: {model}")
    
    # Get strategy recommendations
    recommendations = ServiceFactory.get_strategy_recommendations({})
    
    print(f"\n💡 Strategy Recommendations:")
    print(f"   Recommended: {recommendations['recommended_strategy']}")
    print(f"   Reasoning:")
    for reason in recommendations['reasoning']:
        print(f"     • {reason}")
    
    if recommendations['performance_notes']:
        print(f"   Performance Notes:")
        for note in recommendations['performance_notes']:
            print(f"     • {note}")
    
    if recommendations['alternatives']:
        print(f"   Alternatives:")
        for alt in recommendations['alternatives']:
            print(f"     • {alt['strategy']}: {alt['note']}")


async def example_unified_configuration():
    """Example 3: Using unified configuration system"""
    print("\n" + "="*60)
    print("Example 3: Unified Configuration System")
    print("="*60)
    
    # Try to load unified configuration
    config_paths = [
        "config/maestrocat_unified.yaml",
        "config/maestrocat_macos.yaml",  # Legacy fallback
        "config/maestrocat.yaml"         # Legacy fallback
    ]
    
    config = None
    for config_path in config_paths:
        if Path(config_path).exists():
            print(f"📄 Loading configuration from: {config_path}")
            try:
                if "unified" in config_path:
                    config = UnifiedMaestroCatConfig.from_file(config_path)
                else:
                    config = UnifiedMaestroCatConfig.from_legacy_file(config_path)
                break
            except Exception as e:
                print(f"⚠️  Failed to load {config_path}: {e}")
    
    if not config:
        print(f"🔧 No configuration file found, using auto-load...")
        config = UnifiedMaestroCatConfig.auto_load()
    
    print(f"✅ Configuration loaded successfully!")
    print(f"   Platform Type: {config.platform_type.value if config.platform_type else 'auto'}")
    print(f"   STT Service: {config.stt.service}")
    print(f"   LLM Model: {config.llm.model}")
    print(f"   TTS Service: {config.tts.service}")
    
    # Create agent with this configuration
    agent = MaestroCatAgent(config=config)
    
    print(f"\n🎭 Created unified agent with platform: {agent.platform_info.description}")


async def example_platform_override():
    """Example 4: Platform override and validation"""
    print("\n" + "="*60)
    print("Example 4: Platform Override and Validation")
    print("="*60)
    
    # Try different platforms to show flexibility
    platforms_to_try = [PlatformType.MACOS_NATIVE, PlatformType.DOCKER]
    
    for platform_type in platforms_to_try:
        print(f"\n🎯 Trying platform: {platform_type.value}")
        
        try:
            # Create strategy for validation
            dummy_config = UnifiedMaestroCatConfig({}, platform_type, auto_detect_platform=False)
            strategy = ServiceFactory.create_strategy(platform_type, dummy_config)
            
            # Validate compatibility
            is_compatible, issues = ServiceFactory.validate_strategy_compatibility(strategy)
            
            if is_compatible:
                print(f"   ✅ Platform {platform_type.value} is compatible")
                
                # Create agent with platform override
                agent = MaestroCatAgent(platform_override=platform_type)
                print(f"   🎭 Created agent for {platform_type.value}")
                print(f"   📋 Platform: {agent.platform_info.description}")
                
                await agent.cleanup()
                
            else:
                print(f"   ❌ Platform {platform_type.value} has issues:")
                for issue in issues:
                    print(f"      • {issue}")
                    
        except Exception as e:
            print(f"   ⚠️  Failed to create {platform_type.value} strategy: {e}")


async def example_migration():
    """Example 5: Configuration migration"""
    print("\n" + "="*60)
    print("Example 5: Configuration Migration")
    print("="*60)
    
    # Check if legacy configurations exist
    docker_config = Path("config/maestrocat.yaml")
    macos_config = Path("config/maestrocat_macos.yaml")
    unified_config = Path("config/maestrocat_unified.yaml")
    
    print(f"📋 Configuration Status:")
    print(f"   Docker config: {'✅' if docker_config.exists() else '❌'} {docker_config}")
    print(f"   macOS config: {'✅' if macos_config.exists() else '❌'} {macos_config}")
    print(f"   Unified config: {'✅' if unified_config.exists() else '❌'} {unified_config}")
    
    if (docker_config.exists() or macos_config.exists()) and not unified_config.exists():
        print(f"\n🔄 Legacy configurations found, demonstrating migration...")
        
        # Show how migration would work (don't actually migrate)
        print(f"   Migration would:")
        print(f"   1. Load legacy configurations")
        print(f"   2. Merge into unified format")
        print(f"   3. Write to config/maestrocat_unified.yaml")
        print(f"   4. Create backups of legacy files")
        
        print(f"\n💡 To perform actual migration, run:")
        print(f"   from core.platform.migration import ConfigMigrator")
        print(f"   ConfigMigrator.migrate_legacy_config()")
        
    elif unified_config.exists():
        print(f"\n✅ Unified configuration already exists!")
        
        # Show unified config in action
        config = UnifiedMaestroCatConfig.from_file(unified_config)
        print(f"   Platform type: {config.platform_type.value if config.platform_type else 'auto'}")
        print(f"   Supports platform sections: {'platforms' in config.raw_config}")
        
    else:
        print(f"\n🔧 No configuration files found - would use defaults")


async def example_health_monitoring():
    """Example 6: Health monitoring and debugging"""
    print("\n" + "="*60)
    print("Example 6: Health Monitoring and Debugging")
    print("="*60)
    
    # Create agent
    agent = MaestroCatAgent()
    
    # Setup agent
    setup_success = await agent.setup()
    
    if setup_success:
        # Get comprehensive health information
        health_info = agent.strategy.get_health_info()
        
        print(f"🏥 Health Monitoring Information:")
        print(f"   Platform: {health_info['platform_type']}")
        print(f"   Services Created: {health_info['services_created']}")
        print(f"   Dependencies Checked: {health_info['dependencies_checked']}")
        
        # Show capabilities
        capabilities = health_info['capabilities']
        print(f"   Capabilities:")
        for cap, value in capabilities.items():
            print(f"     {cap}: {value}")
        
        # Platform-specific health info
        platform_specific = {k: v for k, v in health_info.items() 
                           if k not in ['platform_type', 'services_created', 'dependencies_checked', 'capabilities']}
        if platform_specific:
            print(f"   Platform-specific:")
            for key, value in platform_specific.items():
                print(f"     {key}: {value}")
        
        # Show debug information
        debug_info = agent.strategy.get_debug_info()
        print(f"\n🐛 Debug Information:")
        print(f"   Service specs: {debug_info['service_specs']}")
        
    else:
        print(f"❌ Agent setup failed - health monitoring unavailable")
    
    # Cleanup
    await agent.cleanup()


async def main():
    """Run all examples"""
    print("🎭 MaestroCat Unified Platform Abstraction Examples")
    print("This demonstrates the new unified system that works across all platforms")
    
    examples = [
        example_basic_usage,
        example_platform_detection,
        example_unified_configuration,
        example_platform_override,
        example_migration,
        example_health_monitoring
    ]
    
    for example_func in examples:
        try:
            await example_func()
        except Exception as e:
            logger.error(f"Example {example_func.__name__} failed: {e}")
        
        # Pause between examples
        await asyncio.sleep(1)
    
    print("\n" + "="*60)
    print("🎉 All examples completed!")
    print("💡 Try the unified launcher: python maestrocat_unified.py")
    print("📚 See PLATFORM_ABSTRACTION.md for full documentation")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())