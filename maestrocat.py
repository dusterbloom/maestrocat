#!/usr/bin/env python3
"""
MaestroCat Universal Launcher
Automatically detects platform and starts the appropriate agent configuration.
"""

import asyncio
import platform
import subprocess
import sys
import os
from pathlib import Path

def detect_platform():
    """Detect the current platform and return the appropriate configuration"""
    system = platform.system().lower()
    
    if system == "darwin":  # macOS
        return "macos"
    elif system == "linux":
        # Check if running in WSL
        try:
            with open("/proc/version", "r") as f:
                version_info = f.read().lower()
                if "microsoft" in version_info or "wsl" in version_info:
                    return "wsl"
        except FileNotFoundError:
            pass
        return "linux"
    else:
        return "unknown"

def check_dependencies(platform_type):
    """Check if required dependencies are available for the platform"""
    missing = []
    
    if platform_type == "macos":
        # Check native macOS dependencies
        try:
            # Check Ollama
            result = subprocess.run(
                ["curl", "-s", "http://localhost:11434/api/version"], 
                capture_output=True, 
                timeout=2
            )
            if result.returncode != 0:
                missing.append("Ollama not running (start with: ollama serve)")
        except:
            missing.append("Ollama not available (install with: brew install ollama)")
        
        # Check Whisper.cpp (try multiple binary names)
        whisper_found = False
        for whisper_cmd in ["whisper-cpp", "whisper"]:
            try:
                subprocess.run([whisper_cmd, "--help"], capture_output=True, check=True)
                whisper_found = True
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        
        if not whisper_found:
            missing.append("whisper.cpp (install with: brew install whisper-cpp)")
        
        # Check macOS say command (just check if it exists, no --help)
        try:
            subprocess.run(["which", "say"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("macOS 'say' command not available")
            
    else:
        # Check Docker dependencies for Linux/WSL/Windows
        try:
            result = subprocess.run(["docker", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("Docker (install from: https://docker.com)")
        
        try:
            result = subprocess.run(["docker-compose", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("Docker Compose (install with: pip install docker-compose)")
    
    return missing

def get_config_and_example(platform_type):
    """Get the appropriate config file and example script for the platform"""
    if platform_type == "macos":
        return "config/maestrocat_macos.yaml", "examples/local_maestrocat_macos.py"
    else:
        return "config/maestrocat.yaml", "examples/local_maestrocat_agent.py"

def print_platform_info(platform_type, config_file, example_file):
    """Print platform-specific information"""
    print("🎭 MaestroCat Universal Launcher")
    print("=" * 50)
    
    if platform_type == "macos":
        print("🍎 Detected: macOS (Apple Silicon optimized)")
        print("🚀 Using: Native services (Whisper.cpp + Ollama + macOS TTS)")
        print("⚡ Performance: Metal acceleration enabled")
    elif platform_type == "wsl":
        print("🐧 Detected: Windows Subsystem for Linux")
        print("🐳 Using: Docker services (WhisperLive + Ollama + Kokoro)")
        print("🔊 Audio: WSL audio transport")
    elif platform_type == "linux":
        print("🐧 Detected: Linux")
        print("🐳 Using: Docker services (WhisperLive + Ollama + Kokoro)")
        print("🎵 Audio: PyAudio transport")
    elif platform_type == "windows":
        print("🪟 Detected: Windows")
        print("🐳 Using: Docker services (WhisperLive + Ollama + Kokoro)")
        print("🎵 Audio: Windows audio transport")
    else:
        print(f"❓ Detected: {platform_type} (unknown)")
        print("🐳 Using: Docker services (fallback)")
    
    print("")
    print(f"📄 Config: {config_file}")
    print(f"🎯 Script: {example_file}")
    print("=" * 50)

def print_setup_instructions(platform_type, missing_deps):
    """Print setup instructions for missing dependencies"""
    if not missing_deps:
        return
        
    print("❌ Missing Dependencies:")
    for dep in missing_deps:
        print(f"   • {dep}")
    print("")
    
    if platform_type == "macos":
        print("🔧 macOS Setup Commands:")
        print("   brew install ollama whisper-cpp ffmpeg")
        print("   ollama serve &")
        print("   ollama pull llama3.2:3b")
        print("")
    else:
        print("🔧 Docker Setup Commands:")
        print("   docker-compose up -d")
        print("   docker-compose ps  # Check services")
        print("")

async def main():
    """Main launcher function"""
    # Detect platform
    platform_type = detect_platform()
    
    # Get appropriate configuration
    config_file, example_file = get_config_and_example(platform_type)
    
    # Print platform info
    print_platform_info(platform_type, config_file, example_file)
    
    # Check dependencies
    missing_deps = check_dependencies(platform_type)
    
    if missing_deps:
        print_setup_instructions(platform_type, missing_deps)
        print("❗ Please install missing dependencies and try again.")
        return 1
    
    # Check if config and example files exist
    if not os.path.exists(config_file):
        print(f"❌ Config file not found: {config_file}")
        return 1
        
    if not os.path.exists(example_file):
        print(f"❌ Example file not found: {example_file}")
        return 1
    
    print("✅ All dependencies available!")
    print("")
    print("🚀 Starting MaestroCat...")
    print(f"💻 Platform: {platform_type}")
    
    if platform_type == "macos":
        print("🎤 STT: Whisper.cpp (native)")
        print("🧠 LLM: Ollama (native)")
        print("🗣️  TTS: macOS System (native)")
        print("🌐 WebSocket: http://localhost:8765/ws")
        print("🐛 Debug UI: http://localhost:8080")
    else:
        print("🎤 STT: WhisperLive (Docker)")
        print("🧠 LLM: Ollama (Docker)")
        print("🗣️  TTS: Kokoro (Docker)")
        print("🌐 WebSocket: http://localhost:8765/ws")
        print("🐛 Debug UI: http://localhost:8080")
    
    print("")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    # Import and run the appropriate example
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    try:
        if platform_type == "macos":
            from examples.local_maestrocat_macos import MacOSMaestroCatAgent
            agent = MacOSMaestroCatAgent(config_file)
        else:
            from examples.local_maestrocat_agent import LocalMaestroCatAgent
            agent = LocalMaestroCatAgent(config_file)
        
        await agent.run()
        
    except KeyboardInterrupt:
        print("\n👋 MaestroCat shutting down...")
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1

def cli():
    """Command line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="MaestroCat Universal Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    maestrocat                    # Auto-detect platform and start
    python maestrocat.py          # Same as above
    python -m maestrocat          # Module execution
    
Platform Detection:
    • macOS: Uses native Whisper.cpp + Ollama + macOS TTS
    • Linux: Uses Docker services (WhisperLive + Ollama + Kokoro)
    • WSL: Uses Docker services with WSL audio transport
    • Windows: Uses Docker services with Windows audio transport
        """
    )
    
    parser.add_argument(
        "--platform", 
        choices=["macos", "linux", "wsl", "windows"],
        help="Force specific platform instead of auto-detection"
    )
    
    parser.add_argument(
        "--config",
        help="Path to custom config file"
    )
    
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check dependencies, don't start the agent"
    )
    
    args = parser.parse_args()
    
    # Override platform detection if specified
    if args.platform:
        platform_type = args.platform
    else:
        platform_type = detect_platform()
    
    # Override config if specified
    if args.config:
        config_file = args.config
        example_file = get_config_and_example(platform_type)[1]
    else:
        config_file, example_file = get_config_and_example(platform_type)
    
    print_platform_info(platform_type, config_file, example_file)
    
    # Check dependencies
    missing_deps = check_dependencies(platform_type)
    
    if missing_deps:
        print_setup_instructions(platform_type, missing_deps)
        return 1
    
    if args.check_only:
        print("✅ All dependencies available!")
        return 0
    
    # Run the agent
    return asyncio.run(main())

if __name__ == "__main__":
    exit_code = cli()
    sys.exit(exit_code)