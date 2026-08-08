from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sayra.common.datetime import utc_now
from sayra.common.decorators import with_db_session
from sayra.common.identifiers import IdType, new_id
from sayra.core.db.models import AudioAsset, ConversationSession, Turn
from sayra.core.enums import ACTIVE_TURN_STATUSES, SessionStatus
from sayra.core.exceptions import ConflictError, NotFoundError


@with_db_session
async def insert_session(
    db: AsyncSession, values: Mapping[str, Any]
) -> ConversationSession:
    session = ConversationSession(
        id=new_id(IdType.SESSION),
        **values,
        conversation_summary=None,
        summary_until_turn_index=0,
        next_turn_index=1,
        status=SessionStatus.ACTIVE,
        last_active_at=utc_now(),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@with_db_session
async def select_session_by_id(db: AsyncSession, session_id: str) -> ConversationSession:
    session = await db.get(ConversationSession, session_id)
    if not session:
        raise NotFoundError(f"Session {session_id} does not exist")
    return session


@with_db_session
async def select_sessions_page(
    db: AsyncSession, offset: int, limit: int
) -> tuple[Sequence[ConversationSession], int]:
    visible = ConversationSession.status != SessionStatus.DELETING
    sessions = (
        await db.scalars(
            select(ConversationSession)
            .where(visible)
            .order_by(ConversationSession.last_active_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    total = await db.scalar(select(func.count(ConversationSession.id)).where(visible))
    return sessions, int(total or 0)


@with_db_session
async def update_session_for_deletion_by_id(
    db: AsyncSession, session_id: str
) -> list[str]:
    session = await db.scalar(
        select(ConversationSession)
        .where(ConversationSession.id == session_id)
        .with_for_update()
    )
    if not session:
        raise NotFoundError(f"Session {session_id} does not exist")
    active_turn = await db.scalar(
        select(Turn).where(
            Turn.session_id == session_id,
            Turn.status.in_(ACTIVE_TURN_STATUSES),
        )
    )
    if active_turn:
        raise ConflictError(
            f"Cannot delete session while turn {active_turn.id} is active"
        )
    file_paths = list(
        (
            await db.scalars(
                select(AudioAsset.file_path).where(AudioAsset.session_id == session_id)
            )
        ).all()
    )
    session.status = SessionStatus.DELETING
    await db.commit()
    return file_paths


@with_db_session
async def update_session_deletion_result_by_id(
    db: AsyncSession, session_id: str, *, failed: bool
) -> None:
    session = await db.get(ConversationSession, session_id)
    if not session:
        return
    if failed:
        session.status = SessionStatus.DELETE_FAILED
    else:
        await db.delete(session)
    await db.commit()


@with_db_session
async def select_failed_session_deletion_ids(db: AsyncSession) -> Sequence[str]:
    return (
        await db.scalars(
            select(ConversationSession.id).where(
                ConversationSession.status == SessionStatus.DELETE_FAILED
            )
        )
    ).all()
