"""
Platform Detection System

Automatically detects the current platform and its capabilities to select
the most appropriate platform strategy. Provides detailed capability assessment
to optimize service selection and configuration.
"""

import platform
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .strategy import PlatformType, PlatformCapabilities, PlatformInfo


class PlatformDetector:
    """
    Detects current platform and capabilities to determine the best platform strategy.
    
    Detection includes:
    - Operating system and architecture
    - Available hardware acceleration (GPU, Metal, MLX)
    - Docker availability and status
    - Native service availability
    - Performance characteristics
    """
    
    @staticmethod
    def detect_platform_type() -> PlatformType:
        """Detect the basic platform type"""
        system = platform.system().lower()
        
        if system == "darwin":
            return PlatformType.MACOS_NATIVE
        elif system == "linux":
            # Check if running in WSL
            try:
                with open("/proc/version", "r") as f:
                    version_info = f.read().lower()
                    if "microsoft" in version_info or "wsl" in version_info:
                        return PlatformType.WSL
            except FileNotFoundError:
                pass
            return PlatformType.DOCKER  # Default to Docker for Linux
        elif system == "windows":
            return PlatformType.WINDOWS
        else:
            return PlatformType.DOCKER  # Fallback to Docker
    
    @staticmethod
    def detect_gpu_capabilities() -> Dict[str, bool]:
        """Detect available GPU acceleration"""
        capabilities = {
            "nvidia_gpu": False,
            "amd_gpu": False, 
            "intel_gpu": False,
            "metal": False,
            "mlx": False
        }
        
        # Check for NVIDIA GPU
        try:
            result = subprocess.run(
                ["nvidia-smi"], 
                capture_output=True, 
                check=True,
                timeout=5
            )
            capabilities["nvidia_gpu"] = True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Check for Metal (macOS)
        if platform.system() == "Darwin":
            try:
                # Check if Metal is available via system_profiler
                result = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if "Metal" in result.stdout:
                    capabilities["metal"] = True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        # Check for MLX (Apple Silicon)
        try:
            import mlx
            capabilities["mlx"] = True
        except ImportError:
            pass
        
        return capabilities
    
    @staticmethod
    def detect_docker_availability() -> Dict[str, bool]:
        """Detect Docker availability and status"""
        docker_info = {
            "docker_installed": False,
            "docker_running": False,
            "docker_compose": False
        }
        
        # Check Docker installation
        try:
            result = subprocess.run(
                ["docker", "--version"], 
                capture_output=True, 
                check=True,
                timeout=5
            )
            docker_info["docker_installed"] = True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return docker_info
        
        # Check if Docker daemon is running
        try:
            result = subprocess.run(
                ["docker", "ps"], 
                capture_output=True, 
                check=True,
                timeout=10
            )
            docker_info["docker_running"] = True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        
        # Check Docker Compose
        try:
            result = subprocess.run(
                ["docker-compose", "--version"], 
                capture_output=True, 
                check=True,
                timeout=5
            )
            docker_info["docker_compose"] = True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            # Try newer docker compose syntax
            try:
                result = subprocess.run(
                    ["docker", "compose", "version"], 
                    capture_output=True, 
                    check=True,
                    timeout=5
                )
                docker_info["docker_compose"] = True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
        
        return docker_info
    
    @staticmethod
    def detect_native_services() -> List[str]:
        """Detect available native services"""
        services = []
        
        # Check for Ollama
        try:
            result = subprocess.run(
                ["ollama", "--version"], 
                capture_output=True, 
                check=True,
                timeout=5
            )
            services.append("ollama")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Check for Whisper.cpp (check both old and new binary names)
        whisper_binaries = ["whisper-cli", "whisper-cpp", "whisper"]
        whisper_found = False
        
        for binary in whisper_binaries:
            try:
                result = subprocess.run(
                    [binary, "--help"], 
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    services.append("whisper-cpp")
                    whisper_found = True
                    break
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue
        
        # Also check via 'which' command
        if not whisper_found:
            for binary in whisper_binaries:
                try:
                    result = subprocess.run(
                        ["which", binary], 
                        capture_output=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        services.append("whisper-cpp")
                        break
                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                    continue
        
        # Check for macOS say command
        if platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ["which", "say"], 
                    capture_output=True, 
                    check=True,
                    timeout=5
                )
                services.append("macos-tts")
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        # Check for FFmpeg
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], 
                capture_output=True, 
                check=True,
                timeout=5
            )
            services.append("ffmpeg")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        return services
    
    @classmethod
    def detect_full_platform_info(cls) -> PlatformInfo:
        """Perform complete platform detection and return comprehensive info"""
        platform_type = cls.detect_platform_type()
        gpu_caps = cls.detect_gpu_capabilities()
        docker_info = cls.detect_docker_availability()
        native_services = cls.detect_native_services()
        
        # Build capabilities
        capabilities = PlatformCapabilities(
            has_gpu=gpu_caps["nvidia_gpu"] or gpu_caps["amd_gpu"] or gpu_caps["intel_gpu"],
            supports_metal=gpu_caps["metal"],
            supports_mlx=gpu_caps["mlx"],
            docker_available=docker_info["docker_running"],
            native_services=native_services
        )
        
        # Generate description and recommendations
        if platform_type == PlatformType.MACOS_NATIVE:
            description = "macOS with native services"
            if capabilities.supports_mlx:
                description += " (Apple Silicon with MLX acceleration)"
            recommended_models = {
                "stt": "base" if capabilities.supports_mlx else "tiny",
                "llm": "llama3.2:3b" if capabilities.supports_mlx else "llama3.2:1b",
                "tts": "af_bella"
            }
        elif platform_type == PlatformType.DOCKER:
            description = "Linux with Docker services"
            if capabilities.has_gpu:
                description += " (GPU-accelerated)"
            recommended_models = {
                "stt": "small" if capabilities.has_gpu else "tiny",
                "llm": "llama3.2:3b" if capabilities.has_gpu else "llama3.2:1b", 
                "tts": "af_bella"
            }
        elif platform_type == PlatformType.WSL:
            description = "Windows Subsystem for Linux with Docker services"
            recommended_models = {
                "stt": "tiny",
                "llm": "llama3.2:1b",
                "tts": "af_bella"
            }
        else:
            description = f"Unknown platform ({platform.system()})"
            recommended_models = {
                "stt": "tiny",
                "llm": "llama3.2:1b", 
                "tts": "af_bella"
            }
        
        return PlatformInfo(
            platform_type=platform_type,
            capabilities=capabilities,
            description=description,
            recommended_models=recommended_models
        )
    
    @classmethod 
    def should_prefer_native(cls, platform_info: PlatformInfo) -> bool:
        """Determine if native services should be preferred over Docker"""
        if platform_info.platform_type == PlatformType.MACOS_NATIVE:
            # Prefer native on macOS if we have key native services
            required_native = {"ollama", "macos-tts"}
            available_native = set(platform_info.capabilities.native_services)
            return required_native.issubset(available_native)
        
        return False
    
    @classmethod
    def auto_select_strategy_type(cls, platform_info: Optional[PlatformInfo] = None) -> PlatformType:
        """
        Automatically select the best platform strategy based on detected capabilities.
        
        Selection logic:
        1. macOS with native services -> MacOS Native Strategy
        2. Linux/WSL with Docker -> Docker Strategy  
        3. Windows -> Docker Strategy (fallback)
        4. Unknown -> Docker Strategy (fallback)
        """
        if platform_info is None:
            platform_info = cls.detect_full_platform_info()
        
        # macOS: prefer native if available, fallback to Docker
        if platform_info.platform_type == PlatformType.MACOS_NATIVE:
            if cls.should_prefer_native(platform_info):
                return PlatformType.MACOS_NATIVE
            elif platform_info.capabilities.docker_available:
                return PlatformType.DOCKER
            else:
                return PlatformType.MACOS_NATIVE  # Try native even if not ideal
        
        # Linux/WSL: prefer Docker if available
        elif platform_info.platform_type in [PlatformType.DOCKER, PlatformType.WSL]:
            if platform_info.capabilities.docker_available:
                return PlatformType.DOCKER
            else:
                # Could implement Linux native strategy in future
                return PlatformType.DOCKER
        
        # Windows: Docker only for now
        elif platform_info.platform_type == PlatformType.WINDOWS:
            return PlatformType.DOCKER
        
        # Fallback to Docker
        return PlatformType.DOCKER