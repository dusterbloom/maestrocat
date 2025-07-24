# test_native_kokoro.py
"""Test script for native Kokoro ONNX TTS service"""

import asyncio
import logging
import time
from core.services.native_kokoro_tts import NativeKokoroTTSService

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_native_kokoro():
    """Test the native Kokoro TTS service"""
    logger.info("🚀 Testing Native Kokoro ONNX TTS Service")
    
    try:
        # Initialize the service
        logger.info("Initializing TTS service...")
        tts = NativeKokoroTTSService(
            voice="af_bella",  # Use one of the available voices
            speed=1.0,
            sample_rate=24000
        )
        
        # Test text
        test_text = "Hello, this is a test of the native Kokoro TTS service on Apple Silicon."
        logger.info(f"Generating speech for: '{test_text}'")
        
        # Measure generation time
        start_time = time.time()
        
        # Generate speech
        frames = []
        async for frame in tts.run_tts(test_text):
            frames.append(frame)
            logger.debug(f"Received frame: {type(frame).__name__}")
        
        generation_time = time.time() - start_time
        
        logger.info(f"✅ Generation completed in {generation_time:.3f}s")
        logger.info(f"Generated {len(frames)} frames")
        
        # Print performance metrics
        chars_per_sec = len(test_text) / generation_time if generation_time > 0 else 0
        logger.info(f"📊 Performance: {chars_per_sec:.1f} chars/sec")
        
        if generation_time < 1.0:
            logger.info("🎉 Sub-second generation achieved!")
        else:
            logger.warning(f"⚠️  Generation took {generation_time:.3f}s (target: <1s)")
            
        # Cleanup
        await tts.stop()
        logger.info("✅ Test completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_native_kokoro())