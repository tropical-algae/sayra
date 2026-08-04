import asyncio
from collections.abc import AsyncIterator, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sayra.app.main import create_app
from sayra.common.config import Settings
from sayra.core.db.session import init_db_models
from sayra.core.prompts.loader import PromptBuilder
from sayra.core.types import (
    AudioChunk,
    AudioInput,
    SpeechRequest,
    StoredFile,
    TranscriptResult,
)
from sayra.core.workflow.conversation import ConversationWorkflow
from sayra.core.workflow.events import EventBroker
from sayra.core.workflow.runtime import WorkflowRuntime


class FakeASR:
    async def transcribe(self, _audio: AudioInput, _language) -> TranscriptResult:
        return TranscriptResult("I go to school yesterday", "asr-request")


class PassthroughAudioNormalizer:
    async def normalize(self, audio: AudioInput) -> AudioInput:
        return audio


class FakeLLM:
    def __init__(self) -> None:
        self.fail_translation_once = False
        self.fail_stream_once = False
        self.fail_refinement_once = False
        self.stream_delay = 0.0

    async def stream_reply(self, _messages) -> AsyncIterator[str]:
        if self.fail_stream_once:
            self.fail_stream_once = False
            raise RuntimeError("temporary main reply failure")
        if self.stream_delay:
            await asyncio.sleep(self.stream_delay)
        yield "That sounds interesting! "
        yield "What did you enjoy most?"

    async def complete(self, messages) -> str:
        instruction = messages[0]["content"]
        if "Correct only obvious speech-recognition" in instruction:
            if self.fail_refinement_once:
                self.fail_refinement_once = False
                raise RuntimeError("temporary refinement failure")
            return messages[-1]["content"]
        if "Translate the supplied text" in instruction:
            if self.fail_translation_once:
                self.fail_translation_once = False
                raise RuntimeError("temporary translation failure")
            return "听起来很有趣！你最喜欢什么？"
        if "possible learner replies" in instruction:
            return (
                '{"suggestions":[{"target_text":"I enjoyed meeting my friends.",'
                '"native_text":"我喜欢和朋友见面。"}]}'
            )
        if "valuable grammar" in instruction:
            return (
                '{"has_guidance":true,"original":"go","corrected":"went",'
                '"explanation":"过去发生的事情使用过去式。"}'
            )
        if "conversation summary" in instruction:
            return "The learner discussed school."
        return "ok"


class FakeTTS:
    async def synthesize(self, request: SpeechRequest) -> AsyncIterator[AudioChunk]:
        yield AudioChunk(
            data=f"audio:{request.text}".encode(),
            sequence=1,
            content_type="audio/mpeg",
        )


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def initialize(self) -> None:
        return None

    async def put(self, file_path: str, data: bytes, content_type: str) -> StoredFile:
        self.objects[file_path] = data
        return StoredFile(file_path, len(data), content_type, "checksum")

    async def stream(self, file_path: str) -> AsyncIterator[bytes]:
        yield self.objects[file_path]

    async def delete(self, file_path: str) -> None:
        self.objects.pop(file_path, None)


class TestContainer:
    __test__ = False

    def __init__(
        self,
        config: Settings,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.config = config
        self.engine = engine
        self.session_factory = session_factory
        self.storage = MemoryStorage()
        self.audio_normalizer = PassthroughAudioNormalizer()
        self.asr = FakeASR()
        self.tts = FakeTTS()
        self.llm = FakeLLM()
        self.prompts = PromptBuilder(config.PROMPT_ROOT)
        self.events = EventBroker(
            session_factory,
            config.LIVE_EVENT_BUFFER_SIZE,
            config.LIVE_AUDIO_EVENT_RETENTION_SECONDS,
            config.EVENT_REPLAY_BATCH_SIZE,
        )
        self.workflow = ConversationWorkflow(
            session_factory,
            self.llm,
            self.tts,
            self.storage,
            self.events,
            self.prompts,
            config,
        )
        self.runtime = WorkflowRuntime(self.workflow)

    async def startup(self) -> None:
        await init_db_models(self.engine)

    async def shutdown(self) -> None:
        await self.runtime.shutdown(2)
        await self.engine.dispose()


@pytest.fixture(scope="session")
def container(tmp_path_factory) -> TestContainer:
    db_path = tmp_path_factory.mktemp("database") / "test.db"
    config = Settings(
        DATABASE_PATH=db_path,
        LLM_API_KEY="test",
        DEFAULT_VOICE_ID="test-voice",
        CONTEXT_SUMMARY_TRIGGER_TURNS=3,
        CONTEXT_RECENT_TURNS=2,
        EVENT_REPLAY_BATCH_SIZE=2,
    )
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    return TestContainer(config, engine, session_factory)


@pytest.fixture(scope="session")
def client(container: TestContainer) -> Generator[TestClient, None, None]:
    with TestClient(create_app(container)) as test_client:
        yield test_client
