from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sayra.common.datetime import utc_now
from sayra.common.identifiers import IdType, new_id
from sayra.core.db.models import AudioAsset, ConversationSession, Turn
from sayra.core.enums import ACTIVE_TURN_STATUSES, SessionStatus, TurnStatus
from sayra.core.exceptions import ConflictError, InvalidStateError, NotFoundError


async def insert_transcription_turn(
    db: AsyncSession, session_id: str, turn_id: str
) -> ConversationSession:
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
    active = await db.scalar(
        select(Turn).where(
            Turn.session_id == session_id,
            Turn.status.in_(ACTIVE_TURN_STATUSES),
        )
    )
    if active:
        raise ConflictError(f"Session already has active turn {active.id}")
    db.add(
        Turn(
            id=turn_id,
            session_id=session_id,
            turn_index=session.next_turn_index,
            status=TurnStatus.TRANSCRIBING,
            trace_id=new_id(IdType.TRACE),
        )
    )
    session.next_turn_index += 1
    session.last_active_at = utc_now()
    await db.commit()
    return session


async def insert_recording_asset(db: AsyncSession, asset: AudioAsset) -> None:
    db.add(asset)
    await db.commit()


async def update_transcription_result_by_turn_id(
    db: AsyncSession,
    turn_id: str,
    raw: str,
    refined: str | None,
    transcript: str,
    auto_submit: bool,
) -> Turn:
    turn = await db.get(Turn, turn_id)
    if not turn:
        raise NotFoundError(f"Turn {turn_id} disappeared")
    turn.raw_transcript = raw
    turn.refined_transcript = refined
    turn.status = TurnStatus.AWAITING_CONFIRMATION
    if auto_submit:
        turn.submitted_text = transcript
        turn.submitted_at = utc_now()
        turn.status = TurnStatus.QUEUED
    await db.commit()
    detailed = await db.scalar(
        select(Turn)
        .where(Turn.id == turn_id)
        .options(selectinload(Turn.suggestions), selectinload(Turn.audio_assets))
    )
    assert detailed is not None
    return detailed


async def update_failed_transcription_by_turn_id(
    db: AsyncSession, turn_id: str, error: BaseException
) -> None:
    turn = await db.get(Turn, turn_id)
    if turn:
        turn.status = TurnStatus.FAILED
        turn.error_code = type(error).__name__
        turn.error_message = str(error)[:2000]
        turn.completed_at = utc_now()
        await db.commit()
