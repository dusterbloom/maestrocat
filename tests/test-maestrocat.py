# tests/test_maestrocat_setup.py
"""
Test script to verify MaestroCat setup and connections
"""

import asyncio
import sys
import httpx
import websockets
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MaestroCatTester:
    """Test all MaestroCat components"""
    
    def __init__(self):
        self.results = {}
        
    async def test_whisperlive(self, host: str = "localhost", port: int = 9090):
        """Test WhisperLive connection"""
        logger.info("Testing WhisperLive STT...")
        
        try:
            url = f"ws://{host}:{port}"
            async with websockets.connect(url, timeout=5) as ws:
                # Send test config
                config = {
                    "uid": "test",
                    "language": "en",
                    "model": "small",
                    "task": "transcribe"
                }
                await ws.send(json.dumps(config))
                
                self.results["whisperlive"] = "✅ Connected"
                logger.info("✅ WhisperLive is running")
                return True
                
        except Exception as e:
            self.results["whisperlive"] = f"❌ Error: {e}"
            logger.error(f"❌ WhisperLive error: {e}")
            return False
            
    async def test_ollama(self, base_url: str = "http://localhost:11434"):
        """Test Ollama connection"""
        logger.info("Testing Ollama LLM...")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}/api/tags")
                response.raise_for_status()
                
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                
                self.results["ollama"] = f"✅ Connected ({len(models)} models)"
                logger.info(f"✅ Ollama is running with models: {models}")
                return True
                
        except Exception as e:
            self.results["ollama"] = f"❌ Error: {e}"
            logger.error(f"❌ Ollama error: {e}")
            return False
            
    async def test_piper(self, base_url: str = "http://localhost:5000"):
        """Test Piper TTS connection"""
        logger.info("Testing Piper TTS...")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}/health")
                response.raise_for_status()
                
                self.results["piper"] = "✅ Connected"
                logger.info("✅ Piper TTS is running")
                return True
                
        except Exception as e:
            self.results["piper"] = f"❌ Error: {e}"
            logger.error(f"❌ Piper TTS error: {e}")
            return False
            
    async def test_redis(self, host: str = "localhost", port: int = 6379):
        """Test Redis connection (optional)"""
        logger.info("Testing Redis...")
        
        try:
            import redis.asyncio as redis
            
            r = redis.Redis(host=host, port=port)
            await r.ping()
            await r.close()
            
            self.results["redis"] = "✅ Connected"
            logger.info("✅ Redis is running")
            return True
            
        except ImportError:
            self.results["redis"] = "⚠️  Redis client not installed"
            logger.warning("⚠️  Redis client not installed (pip install redis)")
            return False
        except Exception as e:
            self.results["redis"] = f"❌ Error: {e}"
            logger.error(f"❌ Redis error: {e}")
            return False
            
    async def test_maestrocat_import(self):
        """Test MaestroCat imports"""
        logger.info("Testing MaestroCat imports...")
        
        try:
            # Test core imports
            from maestrocat import (
                InterruptionHandler,
                MetricsCollector,
                EventEmitter,
                WhisperLiveSTTService,
                OllamaLLMService,
                KokoroTTSService
            )
            
            # Test Pipecat imports
            from pipecat.pipeline.pipeline import Pipeline
            from pipecat.frames.frames import Frame
            
            self.results["maestrocat_imports"] = "✅ All imports successful"
            logger.info("✅ MaestroCat imports working")
            return True
            
        except Exception as e:
            self.results["maestrocat_imports"] = f"❌ Import error: {e}"
            logger.error(f"❌ Import error: {e}")
            return False
            
    async def test_pipeline_creation(self):
        """Test creating a basic pipeline"""
        logger.info("Testing pipeline creation...")
        
        try:
            from pipecat.pipeline.pipeline import Pipeline
            from maestrocat.services import WhisperLiveSTTService, OllamaLLMService
            from maestrocat.processors import MetricsCollector
            
            # Create services
            stt = WhisperLiveSTTService(host="localhost", port=9090)
            llm = OllamaLLMService(model="llama3.2:3b")
            metrics = MetricsCollector()
            
            # Create pipeline
            pipeline = Pipeline([stt, llm, metrics])
            
            self.results["pipeline"] = "✅ Pipeline created"
            logger.info("✅ Pipeline creation successful")
            return True
            
        except Exception as e:
            self.results["pipeline"] = f"❌ Pipeline error: {e}"
            logger.error(f"❌ Pipeline error: {e}")
            return False
            
    async def run_all_tests(self):
        """Run all tests"""
        logger.info("=" * 60)
        logger.info("MaestroCat Setup Test")
        logger.info("=" * 60)
        
        # Test imports first
        await self.test_maestrocat_import()
        
        # Test services
        await self.test_whisperlive()
        await self.test_ollama()
        await self.test_piper()
        await self.test_redis()
        
        # Test pipeline
        await self.test_pipeline_creation()
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("Test Summary:")
        logger.info("=" * 60)
        
        all_passed = True
        for component, result in self.results.items():
            logger.info(f"{component}: {result}")
            if "❌" in result:
                all_passed = False
                
        logger.info("=" * 60)
        
        if all_passed:
            logger.info("✅ All tests passed! MaestroCat is ready to use.")
        else:
            logger.error("❌ Some tests failed. Please check the errors above.")
            
        return all_passed


async def main():
    """Main test runner"""
    tester = MaestroCatTester()
    success = await tester.run_all_tests()
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    import json  # Import at module level for WhisperLive test
    asyncio.run(main())


# Simple usage test
if __name__ == "__main__" and "--simple" in sys.argv:
    # Quick test of basic functionality
    from maestrocat.processors import InterruptionHandler
    
    handler = InterruptionHandler(threshold=0.2)
    print(f"Created interruption handler with threshold: {handler.threshold}")
    print("✅ Basic functionality test passed!")