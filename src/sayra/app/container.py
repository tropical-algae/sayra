from sayra.app.services.session_service import retry_failed_session_deletions
from sayra.common.config import Settings
from sayra.core.db.session import init_db_models, local_engine
from sayra.core.llm import OpenAICompatibleLLM
from sayra.core.prompts.loader import PromptBuilder
from sayra.core.speech.asr import VolcengineASRProvider
from sayra.core.speech.audio import FFmpegAudioNormalizer
from sayra.core.speech.tts import VolcengineTTSProvider
from sayra.core.storage.factory import create_storage
from sayra.core.workflow.events import EventBroker
from sayra.core.workflow.workflow import ConversationWorkflow


class AppContainer:
    def __init__(self, config: Settings) -> None:
        self.config = config
        self.storage = create_storage(config)
        self.audio_normalizer = FFmpegAudioNormalizer(config)
        self.asr = VolcengineASRProvider(config)
        self.tts = VolcengineTTSProvider(config)
        self.llm = OpenAICompatibleLLM(config)
        self.prompts = PromptBuilder(config.PROMPT_ROOT)
        self.events = EventBroker(
            config.LIVE_EVENT_BUFFER_SIZE,
            config.LIVE_AUDIO_EVENT_RETENTION_SECONDS,
            config.EVENT_REPLAY_BATCH_SIZE,
        )
        self.workflow = ConversationWorkflow(
            llm=self.llm,
            tts=self.tts,
            storage=self.storage,
            events=self.events,
            prompts=self.prompts,
            config=config,
        )

    async def startup(self) -> None:
        await init_db_models()
        if self.config.STARTUP_CHECK_STORAGE:
            await self.storage.initialize()
        await self.workflow.recover()
        if self.config.RETRY_FAILED_DELETIONS_ON_STARTUP:
            await retry_failed_session_deletions(self)

    async def shutdown(self) -> None:
        try:
            await self.workflow.shutdown(self.config.TASK_SHUTDOWN_GRACE_SECONDS)
        finally:
            try:
                await self.asr.close()
            finally:
                try:
                    await self.llm.close()
                finally:
                    await local_engine.dispose()
