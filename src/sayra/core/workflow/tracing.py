from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sayra.core.db.crud import trace as trace_crud
from sayra.core.enums import TraceStatus, TraceStep


class TraceRecorder:
    """Persist execution status while providers remain database-agnostic."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    @asynccontextmanager
    async def track(
        self,
        session_id: str,
        turn_id: str | None,
        step: TraceStep,
        provider: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        async with self.session_factory() as db:
            trace_id = await trace_crud.insert_trace(
                db, session_id, turn_id, step, provider, metadata
            )
        try:
            yield trace_id
        except BaseException as exc:
            await self._finish(trace_id, TraceStatus.FAILED, exc)
            raise
        else:
            await self._finish(trace_id, TraceStatus.COMPLETED)

    async def _finish(
        self,
        trace_id: str,
        status: TraceStatus,
        error: BaseException | None = None,
    ) -> None:
        async with self.session_factory() as db:
            await trace_crud.update_trace_status_by_id(db, trace_id, status, error)

    async def annotate(
        self,
        trace_id: str,
        *,
        provider_request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        async with self.session_factory() as db:
            await trace_crud.update_trace_metadata_by_id(
                db, trace_id, provider_request_id, metadata
            )
