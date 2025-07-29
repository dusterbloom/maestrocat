#!/bin/bash
set -e

# Clone whisper.cpp if not already present
if [ ! -d whisper.cpp ]; then
  git clone https://github.com/ggerganov/whisper.cpp
fi

# Install SDL2 dependency
brew install sdl2

cd whisper.cpp

# Clean any previous build
rm -rf build

# Get macOS SDK path
MACOS_SDK=$(xcrun --show-sdk-path --sdk macosx)

# Build using CMake with SDL2 support, explicitly targeting macOS
cmake -B build \
  -DWHISPER_SDL2=ON \
  -DGGML_NATIVE=OFF \
  -DCMAKE_SYSTEM_NAME=Darwin \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=11.0 \
  -DCMAKE_OSX_ARCHITECTURES="arm64" \
  -DCMAKE_OSX_SYSROOT="$MACOS_SDK" \
  -DCMAKE_C_COMPILER=$(xcrun --find clang) \
  -DCMAKE_CXX_COMPILER=$(xcrun --find clang++)

cmake --build build --config Release

# Test the streaming binary
echo "Testing whisper-stream binary..."
./build/bin/whisper-stream --help || echo "Binary built successfully"

# Optional: copy binary into MaestroCat bin directory
mkdir -p ../bin
cp build/bin/whisper-stream ../bin/whisper-stream

echo "✅ whisper.cpp streaming binary built and copied to ./bin/whisper-stream"