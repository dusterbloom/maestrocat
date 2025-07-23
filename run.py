
import asyncio
import logging
import os
from dotenv import load_dotenv

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.aggregators.llm_response import LLMUserContextAggregator, LLMAssistantContextAggregator
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.transports.local.audio import LocalAudioTransportParams

from core.transports.wsl_audio_transport import WSLAudioTransport
from core.processors.module_loader import ModuleLoader
from core.services.ollama_llm import OllamaLLMService
from core.services.whisperlive_stt import WhisperLiveSTTService
from core.services.kokoro_tts import KokoroTTSService
from core.utils.config import MaestroCatConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    load_dotenv()
    # Use the correct Windows host IP for PulseAudio
    os.environ["PULSE_SERVER"] = "tcp:10.255.255.254"

    config = MaestroCatConfig.from_file("config/maestrocat.yaml")

    transport = WSLAudioTransport(
        params=LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_in_device_index=0,  # Use index 0 as per the working script
            audio_out_enabled=True,
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

    context = OpenAILLMContext(messages=[
        {
            "role": "system",
            "content": config.llm.system_prompt,
        }
    ])

    user_context_aggregator = LLMUserContextAggregator(context=context)
    assistant_context_aggregator = LLMAssistantContextAggregator(context=context)

    module_loader = ModuleLoader()

    pipeline = Pipeline([
        transport.input(),
        stt,
        user_context_aggregator,
        llm,
        assistant_context_aggregator,
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
