import asyncio
import base64
from collections import deque
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sayra.core.db.crud import event as event_crud


class ServerEvent(BaseModel):
    session_id: str
    turn_id: str
    sequence: int
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class EventBroker:
    """Persisted event log plus in-process wakeups for reconnect-safe delivery."""

    _TRANSIENT_EVENT_TYPES: ClassVar[frozenset[str]] = frozenset(
        {"assistant.audio.delta"}
    )

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        live_buffer_size: int,
        audio_retention_seconds: float,
        replay_batch_size: int,
    ) -> None:
        self.session_factory = session_factory
        self.live_buffer_size = live_buffer_size
        self.audio_retention_seconds = audio_retention_seconds
        self.replay_batch_size = replay_batch_size
        self._conditions: dict[str, asyncio.Condition] = {}
        self._sequence_locks: dict[str, asyncio.Lock] = {}
        self._latest_sequences: dict[str, int] = {}
        self._live_events: dict[str, deque[ServerEvent]] = {}
        self._cleanup_handles: dict[str, asyncio.TimerHandle] = {}

    def _condition(self, turn_id: str) -> asyncio.Condition:
        return self._conditions.setdefault(turn_id, asyncio.Condition())

    async def emit(
        self,
        session_id: str,
        turn_id: str,
        event_type: str,
        data: dict | None = None,
        audio_data: bytes | None = None,
    ) -> ServerEvent:
        if cleanup := self._cleanup_handles.pop(turn_id, None):
            cleanup.cancel()
        lock = self._sequence_locks.setdefault(turn_id, asyncio.Lock())
        async with lock:
            latest = self._latest_sequences.get(turn_id, 0)
            if event_type in self._TRANSIENT_EVENT_TYPES:
                if latest:
                    sequence = latest + 1
                else:
                    async with self.session_factory() as db:
                        sequence = await event_crud.select_next_event_sequence_by_turn_id(
                            db, turn_id
                        )
            else:
                async with self.session_factory() as db:
                    sequence = await event_crud.insert_event(
                        db, turn_id, event_type, data or {}, latest
                    )
            self._latest_sequences[turn_id] = sequence
        event_data = dict(data or {})
        if audio_data is not None:
            encoded = base64.b64encode(audio_data)
            event_data["audio_base64"] = encoded.decode("ascii")
        event = ServerEvent(
            session_id=session_id,
            turn_id=turn_id,
            sequence=sequence,
            type=event_type,
            data=event_data,
        )
        if audio_data is not None:
            buffer = self._live_events.setdefault(
                turn_id, deque(maxlen=self.live_buffer_size)
            )
            buffer.append(event)
        if event_type in {
            "turn.completed",
            "turn.failed",
            "turn.cancelled",
            "turn.auxiliary_retry.completed",
        } or (event_type.startswith("assistant.") and event_type.endswith(".failed")):
            self._cleanup_handles[turn_id] = asyncio.get_running_loop().call_later(
                self.audio_retention_seconds,
                self._clear_turn_state,
                turn_id,
            )
        async with self._condition(turn_id):
            self._condition(turn_id).notify_all()
        return event

    async def list_after(self, turn_id: str, sequence: int) -> list[ServerEvent]:
        async with self.session_factory() as db:
            records = await event_crud.select_events_by_turn_id_after_sequence(
                db, turn_id, sequence, self.replay_batch_size
            )
        events_by_sequence: dict[int, ServerEvent] = {}
        for record in records:
            events_by_sequence[record.sequence] = ServerEvent(
                session_id="",
                turn_id=turn_id,
                sequence=record.sequence,
                type=record.event_type,
                data=dict(record.data),
            )
        for event in self._live_events.get(turn_id, ()):
            if event.sequence > sequence:
                events_by_sequence[event.sequence] = event.model_copy(deep=True)
        return [
            events_by_sequence[event_sequence]
            for event_sequence in sorted(events_by_sequence)[: self.replay_batch_size]
        ]

    def _clear_turn_state(self, turn_id: str) -> None:
        self._cleanup_handles.pop(turn_id, None)
        self._live_events.pop(turn_id, None)
        self._latest_sequences.pop(turn_id, None)
        self._sequence_locks.pop(turn_id, None)
        self._conditions.pop(turn_id, None)

    async def subscribe(
        self, session_id: str, turn_id: str, after_sequence: int
    ) -> AsyncIterator[ServerEvent]:
        sequence = after_sequence
        terminal_types = {"turn.completed", "turn.failed", "turn.cancelled"}
        while True:
            events = await self.list_after(turn_id, sequence)
            for event in events:
                event.session_id = session_id
                sequence = event.sequence
                yield event
                if event.type in terminal_types:
                    return
            if events:
                continue
            async with self._condition(turn_id):
                try:
                    await asyncio.wait_for(self._condition(turn_id).wait(), timeout=20.0)
                except TimeoutError:
                    yield ServerEvent(
                        session_id=session_id,
                        turn_id=turn_id,
                        sequence=sequence,
                        type="connection.heartbeat",
                        data={},
                    )
