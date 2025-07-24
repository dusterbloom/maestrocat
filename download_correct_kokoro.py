# download_correct_kokoro.py
from huggingface_hub import snapshot_download
import shutil
from pathlib import Path

# Download the correct ONNX model and voices that work together
cache_dir = Path.home() / ".cache" / "kokoro"
cache_dir.mkdir(parents=True, exist_ok=True)

print("Downloading correct Kokoro ONNX model and voices...")

try:
    # Download from onnx-community which has matching voices
    snapshot_download(
        repo_id="onnx-community/Kokoro-82M-ONNX",
        local_dir=str(cache_dir / "onnx-community"),
        allow_patterns=["*.onnx", "*.json", "*.bin", "*.npy"]
    )
    
    print("✅ Downloaded to:", cache_dir / "onnx-community")
    
    # List downloaded files
    onnx_dir = cache_dir / "onnx-community"
    print("\nDownloaded files:")
    for file in sorted(onnx_dir.rglob("*")):
        if file.is_file():
            size_mb = file.stat().st_size / (1024*1024)
            print(f"  {file.relative_to(onnx_dir)}: {size_mb:.1f} MB")
    
except Exception as e:
    print(f"❌ Download failed: {e}")
    print("\nFallback: Download manually from:")
    print("https://huggingface.co/onnx-community/Kokoro-82M-ONNX")