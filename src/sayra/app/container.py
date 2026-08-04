from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sayra.app.services.session_service import retry_failed_session_deletions
from sayra.common.config import Settings
from sayra.core.db.session import LocalSession, init_db_models, local_engine
from sayra.core.llm import OpenAICompatibleLLM
from sayra.core.prompts.loader import PromptBuilder
from sayra.core.speech.asr import VolcengineASRProvider
from sayra.core.speech.audio import FFmpegAudioNormalizer
from sayra.core.speech.tts import VolcengineTTSProvider
from sayra.core.storage.factory import create_storage
from sayra.core.workflow.conversation import ConversationWorkflow
from sayra.core.workflow.events import EventBroker
from sayra.core.workflow.runtime import WorkflowRuntime


class AppContainer:
    def __init__(
        self,
        config: Settings,
        session_factory: async_sessionmaker[AsyncSession] = LocalSession,
        engine: AsyncEngine = local_engine,
    ) -> None:
        self.config = config
        self.session_factory = session_factory
        self.engine = engine
        self.storage = create_storage(config)
        self.audio_normalizer = FFmpegAudioNormalizer(config)
        self.asr = VolcengineASRProvider(config)
        self.tts = VolcengineTTSProvider(config)
        self.llm = OpenAICompatibleLLM(config)
        self.prompts = PromptBuilder(config.PROMPT_ROOT)
        self.events = EventBroker(
            session_factory,
            config.LIVE_EVENT_BUFFER_SIZE,
            config.LIVE_AUDIO_EVENT_RETENTION_SECONDS,
            config.EVENT_REPLAY_BATCH_SIZE,
        )
        self.workflow = ConversationWorkflow(
            session_factory=session_factory,
            llm=self.llm,
            tts=self.tts,
            storage=self.storage,
            events=self.events,
            prompts=self.prompts,
            config=config,
        )
        self.runtime = WorkflowRuntime(self.workflow)

    async def startup(self) -> None:
        await init_db_models(self.engine)
        if self.config.STARTUP_CHECK_STORAGE:
            await self.storage.initialize()
        await self.runtime.recover()
        if self.config.RETRY_FAILED_DELETIONS_ON_STARTUP:
            await retry_failed_session_deletions(self)

    async def shutdown(self) -> None:
        try:
            await self.runtime.shutdown(self.config.TASK_SHUTDOWN_GRACE_SECONDS)
        finally:
            try:
                await self.asr.close()
            finally:
                try:
                    await self.llm.close()
                finally:
                    await self.engine.dispose()
