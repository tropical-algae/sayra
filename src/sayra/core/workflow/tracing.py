from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sayra.core.db.crud import trace as trace_crud
from sayra.core.enums import TraceStatus, TraceStep


@asynccontextmanager
async def track_trace(
    session_id: str,
    turn_id: str | None,
    step: TraceStep,
    provider: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    trace_id = await trace_crud.insert_trace(
        session_id, turn_id, step, provider, metadata
    )
    try:
        yield trace_id
    except BaseException as exc:
        await trace_crud.update_trace_status_by_id(trace_id, TraceStatus.FAILED, exc)
        raise
    else:
        await trace_crud.update_trace_status_by_id(trace_id, TraceStatus.COMPLETED)


async def update_trace(
    trace_id: str,
    *,
    provider_request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    await trace_crud.update_trace_metadata_by_id(trace_id, provider_request_id, metadata)
