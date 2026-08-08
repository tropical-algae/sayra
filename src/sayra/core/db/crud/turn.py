from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sayra.common.datetime import utc_now
from sayra.common.decorators import with_db_session
from sayra.common.identifiers import IdType, new_id
from sayra.core.db.models import ConversationSession, Trace, Turn
from sayra.core.enums import (
    ACTIVE_TURN_STATUSES,
    AuxiliaryTask,
    SessionStatus,
    TaskStatus,
    TurnStatus,
)
from sayra.core.exceptions import ConflictError, InvalidStateError, NotFoundError

_AUXILIARY_STATUS_FIELDS: dict[AuxiliaryTask, str] = {
    AuxiliaryTask.AUDIO: "audio_task_status",
    AuxiliaryTask.TRANSLATION: "translation_task_status",
    AuxiliaryTask.SUGGESTIONS: "suggestions_task_status",
    AuxiliaryTask.GUIDANCE: "guidance_task_status",
}


def _with_details(statement):
    return statement.options(
        selectinload(Turn.suggestions), selectinload(Turn.audio_assets)
    )


@with_db_session
async def select_turn_by_session_and_id(
    db: AsyncSession, session_id: str, turn_id: str
) -> Turn:
    turn = await db.scalar(_with_details(select(Turn).where(Turn.id == turn_id)))
    if not turn or turn.session_id != session_id:
        raise NotFoundError(f"Turn {turn_id} does not exist in session {session_id}")
    return turn


@with_db_session
async def select_turns_by_session_id(
    db: AsyncSession, session_id: str, offset: int, limit: int
) -> tuple[Sequence[Turn], int]:
    if not await db.get(ConversationSession, session_id):
        raise NotFoundError(f"Session {session_id} does not exist")
    turns = (
        await db.scalars(
            _with_details(
                select(Turn)
                .where(Turn.session_id == session_id)
                .order_by(Turn.turn_index)
                .offset(offset)
                .limit(limit)
            )
        )
    ).all()
    total = await db.scalar(
        select(func.count(Turn.id)).where(Turn.session_id == session_id)
    )
    return turns, int(total or 0)


@with_db_session
async def select_traces_by_turn_id(db: AsyncSession, turn_id: str) -> Sequence[Trace]:
    if not await db.get(Turn, turn_id):
        raise NotFoundError(f"Turn {turn_id} does not exist")
    return (
        await db.scalars(
            select(Trace)
            .where(Trace.turn_id == turn_id)
            .order_by(Trace.started_at, Trace.id)
        )
    ).all()


@with_db_session
async def insert_or_update_turn_submission(
    db: AsyncSession,
    session_id: str,
    submitted_text: str,
    turn_id: str | None,
    client_request_id: str | None,
) -> tuple[Turn, bool]:
    session = await db.scalar(
        select(ConversationSession)
        .where(ConversationSession.id == session_id)
        .with_for_update()
    )
    if not session:
        raise NotFoundError(f"Session {session_id} does not exist")
    if session.status != SessionStatus.ACTIVE:
        raise InvalidStateError(
            f"Session {session_id} is {session.status.value} and cannot accept turns"
        )
    if client_request_id:
        existing = await db.scalar(
            _with_details(
                select(Turn).where(
                    Turn.session_id == session_id,
                    Turn.client_request_id == client_request_id,
                )
            )
        )
        if existing:
            return existing, False

    active = await db.scalar(
        select(Turn).where(
            Turn.session_id == session_id,
            Turn.status.in_(ACTIVE_TURN_STATUSES),
        )
    )
    if active and active.id != turn_id:
        raise ConflictError(
            f"Session already has active turn {active.id} ({active.status.value})"
        )
    if turn_id:
        turn = await db.get(Turn, turn_id)
        if not turn or turn.session_id != session_id:
            raise NotFoundError(f"Turn {turn_id} does not exist")
        if turn.status != TurnStatus.AWAITING_CONFIRMATION:
            raise InvalidStateError(
                f"Turn {turn.id} cannot be submitted from {turn.status.value}"
            )
    else:
        turn = Turn(
            id=new_id(IdType.TURN),
            session_id=session_id,
            turn_index=session.next_turn_index,
            status=TurnStatus.QUEUED,
        )
        session.next_turn_index += 1
        db.add(turn)
    turn.submitted_text = submitted_text.strip()
    turn.client_request_id = client_request_id
    turn.status = TurnStatus.QUEUED
    turn.submitted_at = utc_now()
    turn.trace_id = turn.trace_id or new_id(IdType.TRACE)
    turn.assistant_task_status = TaskStatus.PENDING
    session.last_active_at = utc_now()
    await db.commit()
    detailed = await db.scalar(_with_details(select(Turn).where(Turn.id == turn.id)))
    assert detailed is not None
    return detailed, True


@with_db_session
async def update_turn_for_auxiliary_retry_by_id(
    db: AsyncSession, turn_id: str, task: AuxiliaryTask
) -> Turn:
    turn = await db.get(Turn, turn_id)
    if not turn:
        raise NotFoundError(f"Turn {turn_id} does not exist")
    if turn.status != TurnStatus.COMPLETED or not turn.assistant_text:
        raise InvalidStateError(
            "Auxiliary tasks can be retried only after the main reply completes"
        )
    status_field = _AUXILIARY_STATUS_FIELDS[task]
    if getattr(turn, status_field) != TaskStatus.FAILED:
        raise InvalidStateError(f"{task.value} task is not failed and cannot be retried")
    setattr(turn, status_field, TaskStatus.PENDING)
    await db.commit()
    detailed = await db.scalar(_with_details(select(Turn).where(Turn.id == turn_id)))
    assert detailed is not None
    return detailed
