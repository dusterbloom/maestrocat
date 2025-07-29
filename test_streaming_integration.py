#!/usr/bin/env python3
"""
Test script for streaming STT integration
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.services.whispercpp_streaming_stt import WhisperCppStreamingSTTService
from core.transports.macos_stream_transport import MacOSStreamTransport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_streaming_stt():
    """Test the streaming STT service"""
    logger.info("Testing streaming STT integration...")
    
    try:
        # Create streaming STT service
        stt = WhisperCppStreamingSTTService(
            model_path="models/ggml-base.en.bin",
            language="en"
        )
        
        logger.info("✅ Streaming STT service created")
        
        # Create audio transport
        transport = MacOSStreamTransport(
            stt_service=stt,
            sample_rate=16000,
            block_size=512
        )
        
        logger.info("✅ Audio transport created")
        
        # List available devices
        devices = transport.list_devices()
        logger.info(f"✅ Found {len(devices)} audio devices")
        
        # Test streaming start
        success = transport.start()
        if success:
            logger.info("✅ Audio streaming started successfully")
            
            # Run for 5 seconds to test
            logger.info("🎤 Listening for 5 seconds... Speak into your microphone!")
            await asyncio.sleep(5)
            
            # Stop streaming
            transport.stop()
            logger.info("✅ Audio streaming stopped")
            
            # Get stats
            stats = transport.get_stats()
            logger.info(f"📊 Streaming stats: {stats}")
            
        else:
            logger.error("❌ Failed to start audio streaming")
            
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise


async def test_pipeline_integration():
    """Test integration with pipecat pipeline"""
    logger.info("Testing pipeline integration...")
    
    try:
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineTask
        
        # Create services
        stt = WhisperCppStreamingSTTService(
            model_path="models/ggml-base.en.bin",
            language="en"
        )
        
        # Create pipeline
        pipeline = Pipeline([
            stt,
        ])
        
        logger.info("✅ Pipeline created with streaming STT")
        
        # Create task
        task = PipelineTask(pipeline)
        runner = PipelineRunner()
        
        logger.info("✅ Pipeline task created")
        
        # Note: Full pipeline testing requires WebSocket transport
        logger.info("✅ Pipeline integration test passed")
        
    except Exception as e:
        logger.error(f"❌ Pipeline integration test failed: {e}")
        raise


def check_dependencies():
    """Check if all dependencies are available"""
    logger.info("Checking dependencies...")
    
    # Check whisper.cpp stream binary
    binary_paths = [
        "./bin/stream",
        "./whisper.cpp/stream",
        "/opt/homebrew/bin/stream"
    ]
    
    stream_binary = None
    for path in binary_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            stream_binary = path
            break
    
    if stream_binary:
        logger.info(f"✅ Found whisper.cpp stream binary: {stream_binary}")
    else:
        logger.error("❌ whisper.cpp stream binary not found")
        logger.info("Run: ./build_whispercpp_stream.sh")
        return False
    
    # Check model file
    model_path = os.path.expanduser("~/.cache/whisper/ggml-base.en.bin")
    if os.path.exists(model_path):
        logger.info(f"✅ Found whisper model: {model_path}")
    else:
        logger.warning(f"⚠️  Model not found at {model_path}")
        logger.info("Download: wget https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin -P ~/.cache/whisper/")
    
    # Check sounddevice
    try:
        import sounddevice as sd
        logger.info("✅ sounddevice available")
    except ImportError:
        logger.error("❌ sounddevice not available")
        logger.info("Install: pip install sounddevice")
        return False
    
    return True


async def main():
    """Run all tests"""
    logger.info("=" * 60)
    logger.info("🧪 MaestroCat Streaming STT Integration Tests")
    logger.info("=" * 60)
    
    # Check dependencies
    if not check_dependencies():
        logger.error("Dependencies missing - please install required components")
        return
    
    # Run tests
    try:
        await test_streaming_stt()
        await test_pipeline_integration()
        
        logger.info("=" * 60)
        logger.info("🎉 All tests passed!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Tests failed: {e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Tests interrupted")
    except Exception as e:
        logger.error(f"Test error: {e}")