import asyncio
from collections.abc import Awaitable
from typing import TypeVar

import json_repair
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sayra.common.config import Settings
from sayra.common.datetime import utc_now
from sayra.common.identifiers import IdType, new_id
from sayra.core.db.crud import conversation as conversation_crud
from sayra.core.db.crud import runtime as runtime_crud
from sayra.core.db.models import (
    AudioAsset,
    ConversationSession,
    SuggestedReply,
    Turn,
)
from sayra.core.enums import (
    AudioAssetStatus,
    AudioAssetType,
    AuxiliaryTask,
    ConversationMode,
    TaskStatus,
    TraceStep,
)
from sayra.core.exceptions import ProviderError
from sayra.core.prompts.loader import PromptBuilder
from sayra.core.types import (
    FileStorage,
    LLMProvider,
    SpeechRequest,
    TTSProvider,
)
from sayra.core.workflow.events import EventBroker
from sayra.core.workflow.segmenter import SentenceSegmenter
from sayra.core.workflow.tracing import TraceRecorder

T = TypeVar("T")


class ConversationWorkflow:
    """Owns deterministic turn execution and its background task lifecycle."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm: LLMProvider,
        tts: TTSProvider,
        storage: FileStorage,
        events: EventBroker,
        prompts: PromptBuilder,
        config: Settings,
    ) -> None:
        self.session_factory = session_factory
        self.llm = llm
        self.tts = tts
        self.storage = storage
        self.event_broker = events
        self.config = config
        self.prompts = prompts
        self.traces = TraceRecorder(session_factory)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._preserve_on_cancel: set[str] = set()

    def start(self, turn_id: str) -> None:
        existing = self._tasks.get(turn_id)
        if existing and not existing.done():
            return
        task = asyncio.create_task(self._run(turn_id), name=f"turn:{turn_id}")
        self._tasks[turn_id] = task
        task.add_done_callback(lambda completed: self._forget(turn_id, completed))

    def start_retry(self, turn_id: str, task_name: AuxiliaryTask) -> None:
        key = f"{turn_id}:retry:{task_name.value}"
        existing = self._tasks.get(key)
        if existing and not existing.done():
            return
        task = asyncio.create_task(
            self._run_retry(turn_id, task_name),
            name=f"retry:{task_name.value}:{turn_id}",
        )
        self._tasks[key] = task
        task.add_done_callback(lambda completed: self._forget(key, completed))

    def _forget(self, key: str, completed: asyncio.Task[None]) -> None:
        if self._tasks.get(key) is completed:
            self._tasks.pop(key, None)

    async def recover(self) -> None:
        """Recover durable turn state before the API starts accepting traffic."""
        async with self.session_factory() as db:
            turn_ids = await runtime_crud.update_interrupted_tasks_and_select_recoverable_turn_ids(
                db
            )
        for turn_id in turn_ids:
            self.start(turn_id)

    async def _run(self, turn_id: str) -> None:
        try:
            await self.execute_turn(turn_id)
        except Exception:
            logger.exception("Uncaught conversation error for turn {}", turn_id)

    async def _run_retry(self, turn_id: str, task_name: AuxiliaryTask) -> None:
        try:
            await self.retry_auxiliary(turn_id, task_name)
        except Exception:
            logger.exception(
                "Auxiliary retry {} failed for turn {}", task_name.value, turn_id
            )

    async def cancel(self, turn_id: str) -> bool:
        task = self._tasks.get(turn_id)
        if not task or task.done():
            return False
        task.cancel()
        return True

    async def shutdown(self, grace_seconds: float) -> None:
        if not self._tasks:
            return
        _, pending = await asyncio.wait(self._tasks.values(), timeout=grace_seconds)
        task_keys = {task: key for key, task in self._tasks.items()}
        for task in pending:
            key = task_keys.get(task, "")
            if ":retry:" not in key:
                self.preserve_for_restart(key)
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def preserve_for_restart(self, turn_id: str) -> None:
        self._preserve_on_cancel.add(turn_id)

    async def execute_turn(self, turn_id: str) -> dict[str, str]:
        session, turn, history = await self._start_turn(turn_id)
        await self.event_broker.emit(
            session.id, turn.id, "turn.started", {"status": "processing"}
        )
        try:
            assistant_text = await self._run_traced(
                session.id,
                turn.id,
                TraceStep.CONVERSATION,
                self.config.LLM_PROVIDER_NAME,
                self._generate_reply(session, turn, history),
            )
        except asyncio.CancelledError:
            if turn.id in self._preserve_on_cancel:
                self._preserve_on_cancel.discard(turn.id)
                await self._prepare_restart(session.id, turn.id)
            else:
                await self._finish_cancelled(session.id, turn.id)
            raise
        except Exception as exc:
            await self._finish_failed(session.id, turn.id, exc)
            return {"turn_id": turn.id, "status": "failed"}

        auxiliary_tasks = [
            self._run_traced(
                session.id,
                turn.id,
                TraceStep.TRANSLATION,
                self.config.LLM_PROVIDER_NAME,
                self._generate_translation(session, turn, assistant_text),
            ),
            self._run_traced(
                session.id,
                turn.id,
                TraceStep.SUGGESTIONS,
                self.config.LLM_PROVIDER_NAME,
                self._generate_suggestions(session, turn, assistant_text),
            ),
        ]
        if session.conversation_mode == ConversationMode.GUIDED:
            auxiliary_tasks.append(
                self._run_traced(
                    session.id,
                    turn.id,
                    TraceStep.GUIDANCE,
                    self.config.LLM_PROVIDER_NAME,
                    self._generate_guidance(session, turn),
                )
            )
        else:
            await self._set_task_status(
                turn.id, "guidance_task_status", TaskStatus.SKIPPED
            )
        try:
            await asyncio.gather(*auxiliary_tasks, return_exceptions=True)
            await self._run_traced(
                session.id,
                turn.id,
                TraceStep.PERSISTENCE,
                None,
                self._complete_turn(session.id, turn.id),
            )
            await self._maybe_update_summary(session.id, turn.id)
        except asyncio.CancelledError:
            if turn.id in self._preserve_on_cancel:
                self._preserve_on_cancel.discard(turn.id)
                await self._prepare_restart(session.id, turn.id)
            else:
                await self._finish_cancelled(session.id, turn.id)
            raise
        return {"turn_id": turn.id, "status": "completed"}

    async def _start_turn(
        self, turn_id: str
    ) -> tuple[ConversationSession, Turn, list[Turn]]:
        async with self.session_factory() as db:
            (
                session,
                turn,
                history,
                stale_paths,
            ) = await conversation_crud.update_turn_for_workflow_start_by_id(
                db, turn_id, self.config.CONTEXT_RECENT_TURNS
            )
        for file_path in stale_paths:
            try:
                await self.storage.delete(file_path)
            except Exception as exc:  # noqa: PERF203
                logger.warning(
                    "Failed to remove stale workflow file {}: {}", file_path, exc
                )
        return session, turn, history

    async def _generate_reply(
        self, session: ConversationSession, turn: Turn, history: list[Turn]
    ) -> str:
        messages = self.prompts.conversation(session, history, turn.submitted_text or "")
        deltas: list[str] = []
        segmenter = SentenceSegmenter(
            self.config.TTS_SENTENCE_MIN_CHARS,
            self.config.TTS_SENTENCE_MAX_CHARS,
        )
        speech_queue: asyncio.Queue[str | None] = asyncio.Queue()
        audio_task = asyncio.create_task(
            self._generate_audio_traced(session, turn, speech_queue),
            name=f"tts:{turn.id}",
        )
        try:
            async for delta in self.llm.stream_reply(messages):
                deltas.append(delta)
                await self.event_broker.emit(
                    session.id, turn.id, "assistant.text.delta", {"text": delta}
                )
                for sentence in segmenter.feed(delta):
                    await speech_queue.put(sentence)
            remaining = segmenter.flush()
            if remaining:
                await speech_queue.put(remaining)
            await speech_queue.put(None)
        except Exception:
            audio_task.cancel()
            await asyncio.gather(audio_task, return_exceptions=True)
            raise
        text = "".join(deltas).strip()
        if not text:
            audio_task.cancel()
            await asyncio.gather(audio_task, return_exceptions=True)
            raise ProviderError("LLM returned an empty assistant response")
        async with self.session_factory() as db:
            await conversation_crud.update_turn_reply_by_id(db, turn.id, text)
        await self.event_broker.emit(
            session.id, turn.id, "assistant.text.completed", {"text": text}
        )
        await asyncio.gather(audio_task, return_exceptions=True)
        return text

    async def _generate_audio(
        self,
        session: ConversationSession,
        turn: Turn,
        speech_queue: asyncio.Queue[str | None],
    ) -> None:
        await self._set_task_status(turn.id, "audio_task_status", TaskStatus.RUNNING)
        await self.event_broker.emit(session.id, turn.id, "assistant.audio.started")
        audio_parts: list[bytes] = []
        stored = None
        asset_persisted = False
        try:
            segment_index = 0
            while (segment := await speech_queue.get()) is not None:
                segment_index += 1
                request = SpeechRequest(
                    text=segment,
                    language=session.target_language,
                    voice_id=session.voice_id,
                    difficulty=session.difficulty_level,
                )
                async for chunk in self.tts.synthesize(request):
                    audio_parts.append(chunk.data)
                    await self.event_broker.emit(
                        session.id,
                        turn.id,
                        "assistant.audio.delta",
                        {
                            "segment": segment_index,
                            "chunk": chunk.sequence,
                            "content_type": chunk.content_type,
                        },
                        audio_data=chunk.data,
                    )
            if not audio_parts:
                raise ProviderError("TTS returned no audio")
            audio = b"".join(audio_parts)
            file_path = f"sessions/{session.id}/turns/{turn.id}/assistant.mp3"
            stored = await self.storage.put(file_path, audio, "audio/mpeg")
            asset_id = new_id(IdType.AUDIO_ASSET)
            asset = AudioAsset(
                id=asset_id,
                session_id=session.id,
                turn_id=turn.id,
                asset_type=AudioAssetType.ASSISTANT_REPLY,
                file_path=stored.file_path,
                content_type=stored.content_type,
                size_bytes=stored.size_bytes,
                status=AudioAssetStatus.READY,
                checksum_sha256=stored.checksum_sha256,
                created_at=utc_now(),
            )
            async with self.session_factory() as db:
                await conversation_crud.insert_assistant_audio_and_update_turn(
                    db, turn.id, asset
                )
            asset_persisted = True
        except Exception as exc:
            if stored is not None and not asset_persisted:
                try:
                    await self.storage.delete(stored.file_path)
                except Exception as cleanup_error:
                    logger.warning(
                        "Failed to compensate orphaned assistant audio {}: {}",
                        stored.file_path,
                        cleanup_error,
                    )
            await self._auxiliary_failed(
                session.id, turn.id, "audio_task_status", "assistant.audio.failed", exc
            )
            raise
        await self._emit_auxiliary_completed(
            session.id,
            turn.id,
            "assistant.audio.completed",
            {"audio_id": asset_id},
        )

    async def _generate_audio_traced(
        self,
        session: ConversationSession,
        turn: Turn,
        speech_queue: asyncio.Queue[str | None],
    ) -> None:
        await self._run_traced(
            session.id,
            turn.id,
            TraceStep.TTS,
            self.config.TTS_PROVIDER_NAME,
            self._generate_audio(session, turn, speech_queue),
        )

    async def _generate_translation(
        self, session: ConversationSession, turn: Turn, text: str
    ) -> None:
        await self._set_task_status(
            turn.id, "translation_task_status", TaskStatus.RUNNING
        )
        try:
            translation = (
                await self.llm.complete(self.prompts.translation(session, text))
            ).strip()
            if not translation:
                raise ProviderError("LLM returned an empty translation")
            async with self.session_factory() as db:
                await conversation_crud.update_turn_translation_by_id(
                    db, turn.id, translation
                )
        except Exception as exc:
            await self._auxiliary_failed(
                session.id,
                turn.id,
                "translation_task_status",
                "assistant.translation.failed",
                exc,
            )
            raise
        await self._emit_auxiliary_completed(
            session.id,
            turn.id,
            "assistant.translation.completed",
            {"text": translation},
        )

    async def _generate_suggestions(
        self, session: ConversationSession, turn: Turn, text: str
    ) -> None:
        if session.suggestion_count == 0:
            await self._set_task_status(
                turn.id, "suggestions_task_status", TaskStatus.SKIPPED
            )
            return
        await self._set_task_status(
            turn.id, "suggestions_task_status", TaskStatus.RUNNING
        )
        try:
            raw = await self.llm.complete(self.prompts.suggestions(session, text))
            parsed = json_repair.loads(raw)
            if not isinstance(parsed, dict):
                raise ProviderError("LLM returned invalid suggestion JSON")
            items = parsed.get("suggestions", [])
            if len(items) != session.suggestion_count:
                raise ProviderError("LLM returned an invalid suggestion count")
            response_items = []
            suggestions = []
            for index, item in enumerate(items, start=1):
                suggestion = SuggestedReply(
                    id=new_id(IdType.SUGGESTED_REPLY),
                    turn_id=turn.id,
                    sort_order=index,
                    target_text=str(item["target_text"]),
                    native_text=str(item["native_text"]),
                    created_at=utc_now(),
                )
                suggestions.append(suggestion)
                response_items.append(
                    {
                        "id": suggestion.id,
                        "sort_order": index,
                        "target_text": suggestion.target_text,
                        "native_text": suggestion.native_text,
                    }
                )
            async with self.session_factory() as db:
                await conversation_crud.insert_suggestions_and_update_turn(
                    db, turn.id, suggestions
                )
        except Exception as exc:
            await self._auxiliary_failed(
                session.id,
                turn.id,
                "suggestions_task_status",
                "assistant.suggestion.failed",
                exc,
            )
            raise
        for item in response_items:
            await self._emit_auxiliary_completed(
                session.id, turn.id, "assistant.suggestion.completed", item
            )

    async def _generate_guidance(self, session: ConversationSession, turn: Turn) -> None:
        await self._set_task_status(turn.id, "guidance_task_status", TaskStatus.RUNNING)
        try:
            raw = await self.llm.complete(
                self.prompts.guidance(session, turn.submitted_text or "")
            )
            result = json_repair.loads(raw)
            if not isinstance(result, dict):
                raise ProviderError("LLM returned invalid guidance JSON")
            async with self.session_factory() as db:
                await conversation_crud.update_turn_guidance_by_id(db, turn.id, result)
        except Exception as exc:
            await self._auxiliary_failed(
                session.id,
                turn.id,
                "guidance_task_status",
                "assistant.guidance.failed",
                exc,
            )
            raise
        await self._emit_auxiliary_completed(
            session.id, turn.id, "assistant.guidance.completed", result
        )

    async def _emit_auxiliary_completed(
        self,
        session_id: str,
        turn_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        try:
            await self.event_broker.emit(session_id, turn_id, event_type, data)
        except Exception as exc:
            logger.warning(
                "Persisted auxiliary result for turn {} but failed to emit {}: {}",
                turn_id,
                event_type,
                exc,
            )

    async def _complete_turn(self, session_id: str, turn_id: str) -> None:
        async with self.session_factory() as db:
            await conversation_crud.update_completed_turn_and_session(
                db, session_id, turn_id
            )
        await self.event_broker.emit(session_id, turn_id, "turn.completed")

    async def _finish_failed(self, session_id: str, turn_id: str, exc: Exception) -> None:
        logger.exception("Core task failed for turn {}", turn_id)
        async with self.session_factory() as db:
            await conversation_crud.update_failed_turn_by_id(db, turn_id, exc)
        await self.event_broker.emit(
            session_id,
            turn_id,
            "turn.failed",
            {"code": type(exc).__name__, "message": str(exc)},
        )

    async def _finish_cancelled(self, session_id: str, turn_id: str) -> None:
        async with self.session_factory() as db:
            await conversation_crud.update_cancelled_turn_by_id(db, turn_id)
        await self.event_broker.emit(session_id, turn_id, "turn.cancelled")

    async def _prepare_restart(self, session_id: str, turn_id: str) -> None:
        async with self.session_factory() as db:
            await conversation_crud.update_turn_for_restart_by_id(db, turn_id)
        await self.event_broker.emit(
            session_id,
            turn_id,
            "turn.interrupted",
            {"reason": "service_shutdown", "will_resume": True},
        )

    async def _auxiliary_failed(
        self,
        session_id: str,
        turn_id: str,
        field: str,
        event_type: str,
        exc: Exception,
    ) -> None:
        logger.warning("Auxiliary task {} failed for turn {}: {}", field, turn_id, exc)
        await self._set_task_status(turn_id, field, TaskStatus.FAILED)
        await self.event_broker.emit(
            session_id,
            turn_id,
            event_type,
            {"code": type(exc).__name__, "message": str(exc)},
        )

    async def _set_task_status(
        self, turn_id: str, field: str, status: TaskStatus
    ) -> None:
        async with self.session_factory() as db:
            await conversation_crud.update_turn_task_status_by_id(
                db, turn_id, field, status
            )

    async def _maybe_update_summary(self, session_id: str, turn_id: str) -> None:
        async with self.session_factory() as db:
            context = await conversation_crud.select_summary_context_by_session_id(
                db,
                session_id,
                self.config.CONTEXT_SUMMARY_TRIGGER_TURNS,
                self.config.CONTEXT_RECENT_TURNS,
            )
        if context is None:
            return
        old_summary, summarize, last_index = context
        try:
            summary = await self._run_traced(
                session_id,
                turn_id,
                TraceStep.SUMMARY,
                self.config.LLM_PROVIDER_NAME,
                self.llm.complete(self.prompts.summary(old_summary, summarize)),
            )
            async with self.session_factory() as db:
                await conversation_crud.update_session_summary_by_id(
                    db, session_id, summary.strip(), last_index
                )
        except Exception as exc:
            logger.warning("Summary update failed for session {}: {}", session_id, exc)

    async def retry_auxiliary(self, turn_id: str, task: AuxiliaryTask) -> None:
        async with self.session_factory() as db:
            session, turn = await conversation_crud.select_retry_context_by_turn_id(
                db, turn_id
            )
        assistant_text = turn.assistant_text
        assert assistant_text is not None

        if task == AuxiliaryTask.AUDIO:
            segmenter = SentenceSegmenter(
                self.config.TTS_SENTENCE_MIN_CHARS,
                self.config.TTS_SENTENCE_MAX_CHARS,
            )
            queue: asyncio.Queue[str | None] = asyncio.Queue()
            for segment in segmenter.feed(assistant_text):
                await queue.put(segment)
            remaining = segmenter.flush()
            if remaining:
                await queue.put(remaining)
            await queue.put(None)
            await self._run_traced(
                session.id,
                turn.id,
                TraceStep.TTS,
                self.config.TTS_PROVIDER_NAME,
                self._generate_audio(session, turn, queue),
            )
        elif task == AuxiliaryTask.TRANSLATION:
            await self._run_traced(
                session.id,
                turn.id,
                TraceStep.TRANSLATION,
                self.config.LLM_PROVIDER_NAME,
                self._generate_translation(session, turn, assistant_text),
            )
        elif task == AuxiliaryTask.SUGGESTIONS:
            await self._run_traced(
                session.id,
                turn.id,
                TraceStep.SUGGESTIONS,
                self.config.LLM_PROVIDER_NAME,
                self._generate_suggestions(session, turn, assistant_text),
            )
        elif task == AuxiliaryTask.GUIDANCE:
            await self._run_traced(
                session.id,
                turn.id,
                TraceStep.GUIDANCE,
                self.config.LLM_PROVIDER_NAME,
                self._generate_guidance(session, turn),
            )
        await self.event_broker.emit(
            session.id,
            turn.id,
            "turn.auxiliary_retry.completed",
            {"task": task.value},
        )

    async def _run_traced(
        self,
        session_id: str,
        turn_id: str,
        step: TraceStep,
        provider: str | None,
        operation: Awaitable[T],
    ) -> T:
        async with self.traces.track(session_id, turn_id, step, provider):
            return await operation
