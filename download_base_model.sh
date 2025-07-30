#!/bin/bash
# Download smaller Whisper model for better thermal performance

echo "🚀 Downloading Whisper base model for optimized streaming..."

# Create models directory if it doesn't exist
mkdir -p ./mlx_models

# Download base model (142MB) - much smaller than medium (1.4GB)
if [ ! -f "./mlx_models/ggml-base.bin" ]; then
    echo "📥 Downloading ggml-base.bin..."
    curl -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin" \
         -o "./mlx_models/ggml-base.bin" \
         --progress-bar
    echo "✅ Base model downloaded successfully!"
else
    echo "✅ Base model already exists"
fi

# Optional: Download small model (244MB) for slightly better accuracy
read -p "Download small model for better accuracy? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ ! -f "./mlx_models/ggml-small.bin" ]; then
        echo "📥 Downloading ggml-small.bin..."
        curl -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin" \
             -o "./mlx_models/ggml-small.bin" \
             --progress-bar
        echo "✅ Small model downloaded successfully!"
    else
        echo "✅ Small model already exists"
    fi
fi

echo "🎉 Model download complete!"
echo "💡 Tip: Use 'base' model for best thermal performance"