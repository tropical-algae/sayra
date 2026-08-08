from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sayra.common.datetime import utc_now
from sayra.common.decorators import with_db_session
from sayra.common.identifiers import IdType, new_id
from sayra.core.db.models import Trace
from sayra.core.enums import TraceStatus, TraceStep


@with_db_session
async def insert_trace(
    db: AsyncSession,
    session_id: str,
    turn_id: str | None,
    step: TraceStep,
    provider: str | None,
    metadata: dict[str, Any] | None,
) -> str:
    trace_id = new_id(IdType.TRACE)
    previous = await db.scalar(
        select(func.count(Trace.id)).where(
            Trace.session_id == session_id,
            Trace.turn_id == turn_id,
            Trace.step == step,
        )
    )
    db.add(
        Trace(
            id=trace_id,
            session_id=session_id,
            turn_id=turn_id,
            step=step,
            status=TraceStatus.RUNNING,
            provider=provider,
            attempt=int(previous or 0) + 1,
            metadata_json=metadata,
            started_at=utc_now(),
        )
    )
    await db.commit()
    return trace_id


@with_db_session
async def update_trace_status_by_id(
    db: AsyncSession,
    trace_id: str,
    status: TraceStatus,
    error: BaseException | None = None,
) -> None:
    trace = await db.get(Trace, trace_id)
    if trace:
        trace.status = status
        trace.completed_at = utc_now()
        if error:
            trace.error_code = type(error).__name__
            trace.error_message = str(error)[:2000]
        await db.commit()


@with_db_session
async def update_trace_metadata_by_id(
    db: AsyncSession,
    trace_id: str,
    provider_request_id: str | None,
    metadata: dict[str, Any] | None,
) -> None:
    trace = await db.get(Trace, trace_id)
    if trace:
        trace.provider_request_id = provider_request_id
        if metadata is not None:
            trace.metadata_json = metadata
        await db.commit()
