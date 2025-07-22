
import asyncio
import logging
from dotenv import load_dotenv

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.aggregators.llm_context import LLMUserContextAggregator, LLMAssistantContextAggregator
from pipecat.transports.services.local import LocalTransport
from pipecat.vad.silero import SileroVADAnalyzer

from core.processors.interruption import InterruptionHandler
from core.processors.module_loader import ModuleLoader
from core.services.ollama_llm import OllamaLLMService
from core.services.whisperlive_stt import WhisperLiveSTTService
from core.services.kokoro_tts import KokoroTTSService
from core.utils.config import MaestroCatConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    load_dotenv()

    config = MaestroCatConfig.from_file("config/maestrocat.yaml")

    transport = LocalTransport(
        play_audio=True,
        audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(
            params={
                "threshold": config.vad.energy_threshold,
                "min_speech_duration_ms": config.vad.min_speech_ms,
                "max_speech_duration_s": 30.0,
                "min_silence_duration_ms": config.vad.pause_ms,
            }
        )
    )

    stt = WhisperLiveSTTService(
        host=config.stt.host,
        port=config.stt.port,
        language=config.stt.language,
        translate=config.stt.translate,
        model=config.stt.model,
        use_vad=config.stt.use_vad
    )

    llm = OllamaLLMService(
        base_url=config.llm.base_url,
        model=config.llm.model,
        temperature=config.llm.temperature,
        max_tokens=config.llm.max_tokens,
        top_p=config.llm.top_p,
        top_k=config.llm.top_k
    )

    tts = KokoroTTSService(
        base_url=config.tts.base_url,
        voice=config.tts.voice,
        speed=config.tts.speed,
        sample_rate=config.tts.sample_rate
    )

    messages = [
        {
            "role": "system",
            "content": config.llm.system_prompt
        }
    ]

    user_context = LLMUserContextAggregator(messages)
    assistant_context = LLMAssistantContextAggregator(messages)

    interruption_handler = InterruptionHandler(
        threshold=config.interruption.threshold,
        ack_delay=config.interruption.ack_delay,
    )

    module_loader = ModuleLoader()

    pipeline = Pipeline([
        transport.input(),
        stt,
        user_context,
        interruption_handler,
        llm,
        assistant_context,
        tts,
        module_loader,
        transport.output()
    ])

    runner = PipelineRunner()

    task = PipelineTask(pipeline)

    logger.info("Starting MaestroCat terminal agent...")
    await runner.run(task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting...")
