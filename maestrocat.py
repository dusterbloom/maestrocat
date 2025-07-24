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

def check_gpu_availability():
    """Check if NVIDIA GPU is available for Docker"""
    try:
        result = subprocess.run(["nvidia-smi"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def pull_docker_images(platform_type):
    """Pull the appropriate Docker images based on platform"""
    images_to_pull = []
    
    if platform_type == "macos":
        # Skip WhisperLive on macOS since it doesn't support ARM64
        # macOS users should use native Whisper.cpp instead
        images_to_pull = [
            ("ghcr.io/remsky/kokoro-fastapi-cpu:latest", "Kokoro TTS CPU"),
            ("ollama/ollama:latest", "Ollama LLM")
        ]
        print("📥 Pulling ARM64-compatible images for macOS...")
        print("⚠️  Note: WhisperLive skipped (no ARM64 support). Use native Whisper.cpp instead.")
    else:
        # Linux/WSL - check for GPU
        if check_gpu_availability():
            images_to_pull = [
                ("ghcr.io/collabora/whisperlive-gpu:latest", "WhisperLive GPU"),
                ("ghcr.io/remsky/kokoro-fastapi-gpu:latest", "Kokoro TTS GPU"),
                ("ollama/ollama:latest", "Ollama LLM")
            ]
            print("📥 Pulling GPU-accelerated images...")
        else:
            images_to_pull = [
                ("ghcr.io/collabora/whisperlive-cpu:latest", "WhisperLive CPU"),
                ("ghcr.io/remsky/kokoro-fastapi-cpu:latest", "Kokoro TTS CPU"),
                ("ollama/ollama:latest", "Ollama LLM")
            ]
            print("📥 Pulling CPU-only images...")
    
    for image, name in images_to_pull:
        try:
            # Check if image already exists
            result = subprocess.run(
                ["docker", "images", "-q", image], 
                capture_output=True, text=True
            )
            if result.stdout.strip():
                print(f"✅ {name} image already available")
                continue
            
            # Pull the image
            print(f"⬇️  Downloading {name}: {image}")
            result = subprocess.run(
                ["docker", "pull", image], 
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"✅ {name} downloaded successfully")
            else:
                print(f"❌ Failed to pull {name}: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error pulling {name}: {e}")
            return False
    
    return True

def start_docker_services(platform_type):
    """Start all Docker services based on platform"""
    # First, ensure we have all required images
    if not pull_docker_images(platform_type):
        print("❌ Could not download required images")
        return False
    
    if platform_type == "macos":
        print("🍎 Starting macOS-specific Docker services...")
        print("📦 Services: Ollama + Kokoro (CPU-optimized, WhisperLive excluded)")
        cmd = ["docker-compose", "-f", "docker-compose.macos.yml", "up", "-d"]
    else:
        # Linux/WSL - check for GPU
        if check_gpu_availability():
            print("🚀 Starting GPU-accelerated Docker services for Linux/WSL...")
            print("📦 Services: WhisperLive + Ollama + Kokoro (all GPU-accelerated)")
            cmd = ["docker-compose", "-f", "docker-compose.yml", "-f", "docker-compose.gpu.yml", "up", "-d"]
        else:
            print("💻 Starting CPU-only Docker services for Linux/WSL...")
            print("📦 Services: WhisperLive + Ollama + Kokoro (all CPU-only)")
            cmd = ["docker-compose", "-f", "docker-compose.yml", "-f", "docker-compose.cpu.yml", "up", "-d"]
    
    try:
        print(f"🔄 Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Docker services started successfully")
            if platform_type != "macos":
                print("🔊 WhisperLive STT: ws://localhost:9090")
            print("🧠 Ollama LLM: http://localhost:11434")
            if platform_type == "macos":
                print("🗣️  Kokoro TTS: http://localhost:5001")
                print("🌐 Kokoro Web UI: http://localhost:5001/web")
            else:
                print("🗣️  Kokoro TTS: http://localhost:5000")
                print("🌐 Kokoro Web UI: http://localhost:5000/web")
            return True
        else:
            print(f"❌ Failed to start Docker services (exit code {result.returncode})")
            if result.stderr:
                print(f"STDERR: {result.stderr}")
            if result.stdout:
                print(f"STDOUT: {result.stdout}")
            return False
    except Exception as e:
        print(f"❌ Error starting Docker services: {e}")
        return False

def check_dependencies(platform_type):
    """Check if required dependencies are available for the platform"""
    missing = []
    
    if platform_type == "macos":
        # macOS uses native services, check for native dependencies
        try:
            result = subprocess.run(["ollama", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("Ollama (install with: brew install ollama)")
        
        try:
            result = subprocess.run(["whisper-cpp", "--help"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("Whisper.cpp (install with: brew install whisper-cpp)")
        
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("FFmpeg (install with: brew install ffmpeg)")
    else:
        # Linux/WSL/Windows use Docker services
        try:
            result = subprocess.run(["docker", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("Docker (install from: https://docker.com)")
        
        try:
            result = subprocess.run(["docker-compose", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("Docker Compose (install with: pip install docker-compose)")
        
        # Check if Docker daemon is running
        try:
            result = subprocess.run(["docker", "ps"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append("Docker daemon not running (start Docker Desktop or run: sudo systemctl start docker)")
    
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
        print("🚀 Using: Native services (Whisper.cpp + Ollama + Kokoro-onnx )")
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
    
    # Start Docker services only for non-macos platforms
    if platform_type != "macos":
        print("🔧 Starting Docker services...")
        if not start_docker_services(platform_type):
            print("❗ Warning: Could not start Docker services. Please check Docker installation.")
    
    print("")
    print("🚀 Starting MaestroCat...")
    print(f"💻 Platform: {platform_type}")
    
    # Platform-specific service information
    if platform_type == "macos":
        print("🎤 STT: Native Whisper.cpp (Apple Silicon optimized)")
        print("🧠 LLM: Native Ollama (Apple Silicon optimized)")
        print("🗣️  TTS: Native macOS TTS")
    elif check_gpu_availability():
        print("🎤 STT: WhisperLive (Docker, GPU-accelerated)")
        print("🧠 LLM: Ollama (Docker, GPU-accelerated)")
        print("🗣️  TTS: Kokoro (Docker, GPU-accelerated)")
    else:
        print("🎤 STT: WhisperLive (Docker, CPU-only)")
        print("🧠 LLM: Ollama (Docker, CPU-only)")
        print("🗣️  TTS: Kokoro (Docker, CPU-only)")
        
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
    
    parser.add_argument(
        "--start-docker",
        action="store_true",
        help="Only start Docker services, don't run the agent"
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
        
    if args.start_docker:
        if platform_type == "macos":
            print("❌ Docker services are not used on macOS - native services are used instead")
            return 1
        
        print("🔧 Starting Docker services with Debug UI...")
        if start_docker_services(platform_type):
            print("✅ Docker services started successfully!")
            print("🔍 Check status with: docker-compose ps")
            print("")
            
            # Start debug UI server
            from core.apps.debug_ui import DebugUIServer
            debug_port = 8080
            print(f"🐛 Starting Debug UI on http://localhost:{debug_port}")
            print("💡 Debug UI will show live data when MaestroCat agent connects")
            print("🔄 Leave this running and start the agent in another terminal")
            print("")
            print("Press Ctrl+C to stop")
            
            try:
                server = DebugUIServer(port=debug_port)
                return asyncio.run(server.start())
            except KeyboardInterrupt:
                print("\n👋 Debug UI shutting down...")
                return 0
        else:
            print("❌ Failed to start Docker services")
            return 1
    
    # Run the agent
    return asyncio.run(main())

if __name__ == "__main__":
    exit_code = cli()
    sys.exit(exit_code)