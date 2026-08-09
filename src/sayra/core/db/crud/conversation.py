from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from sayra.common.datetime import utc_now
from sayra.common.decorators import with_db_session
from sayra.core.db.models import AudioAsset, ConversationSession, SuggestedReply, Turn
from sayra.core.enums import AudioAssetType, TaskStatus, TurnStatus


@with_db_session
async def update_turn_for_workflow_start_by_id(
    db: AsyncSession, turn_id: str, recent_turns: int
) -> tuple[ConversationSession, Turn, list[Turn], list[str]]:
    turn = await db.get(Turn, turn_id)
    if not turn:
        raise ValueError(f"Turn {turn_id} does not exist")
    if turn.status not in {TurnStatus.QUEUED, TurnStatus.PROCESSING}:
        raise ValueError(f"Turn {turn_id} cannot start from status {turn.status.value}")
    session = await db.get(ConversationSession, turn.session_id)
    if not session or not turn.submitted_text:
        raise ValueError("Turn has no valid session or submitted text")

    regenerable_types = (
        AudioAssetType.ASSISTANT_REPLY,
        AudioAssetType.SUGGESTED_REPLY,
    )
    stale_paths = list(
        (
            await db.scalars(
                select(AudioAsset.file_path).where(
                    AudioAsset.turn_id == turn.id,
                    AudioAsset.asset_type.in_(regenerable_types),
                )
            )
        ).all()
    )
    await db.execute(delete(SuggestedReply).where(SuggestedReply.turn_id == turn.id))
    await db.execute(
        delete(AudioAsset).where(
            AudioAsset.turn_id == turn.id,
            AudioAsset.asset_type.in_(regenerable_types),
        )
    )
    turn.assistant_text = None
    turn.assistant_translation = None
    turn.guidance_original = None
    turn.guidance_corrected = None
    turn.guidance_explanation = None
    turn.error_code = None
    turn.error_message = None
    turn.completed_at = None
    turn.status = TurnStatus.PROCESSING
    turn.assistant_task_status = TaskStatus.RUNNING
    turn.audio_task_status = TaskStatus.PENDING
    turn.translation_task_status = TaskStatus.PENDING
    turn.suggestions_task_status = (
        TaskStatus.PENDING
        if session.suggestions_auto_generate and session.suggestion_count > 0
        else TaskStatus.SKIPPED
    )
    turn.guidance_task_status = TaskStatus.PENDING
    history = list(
        (
            await db.scalars(
                select(Turn)
                .where(
                    Turn.session_id == session.id,
                    Turn.turn_index < turn.turn_index,
                    Turn.status == TurnStatus.COMPLETED,
                )
                .order_by(Turn.turn_index.desc())
                .limit(recent_turns)
            )
        ).all()
    )
    history.reverse()
    await db.commit()
    db.expunge(session)
    db.expunge(turn)
    for previous in history:
        db.expunge(previous)
    return session, turn, history, stale_paths


@with_db_session
async def update_turn_reply_by_id(db: AsyncSession, turn_id: str, text: str) -> None:
    turn = await db.get(Turn, turn_id)
    if turn:
        turn.assistant_text = text
        turn.assistant_task_status = TaskStatus.COMPLETED
        await db.commit()


@with_db_session
async def insert_assistant_audio_and_update_turn(
    db: AsyncSession, turn_id: str, asset: AudioAsset
) -> None:
    db.add(asset)
    turn = await db.get(Turn, turn_id)
    if turn:
        turn.audio_task_status = TaskStatus.COMPLETED
    await db.commit()


@with_db_session
async def update_turn_translation_by_id(
    db: AsyncSession, turn_id: str, text: str
) -> None:
    turn = await db.get(Turn, turn_id)
    if turn:
        turn.assistant_translation = text
        turn.translation_task_status = TaskStatus.COMPLETED
        await db.commit()


@with_db_session
async def insert_suggestions_and_update_turn(
    db: AsyncSession, turn_id: str, suggestions: Sequence[SuggestedReply]
) -> None:
    db.add_all(suggestions)
    turn = await db.get(Turn, turn_id)
    if turn:
        turn.suggestions_task_status = TaskStatus.COMPLETED
    await db.commit()


@with_db_session
async def update_turn_guidance_by_id(
    db: AsyncSession, turn_id: str, result: dict[str, object]
) -> None:
    turn = await db.get(Turn, turn_id)
    if turn:
        if result.get("has_guidance"):
            turn.guidance_original = str(result.get("original") or "")
            turn.guidance_corrected = str(result.get("corrected") or "")
            turn.guidance_explanation = str(result.get("explanation") or "")
        turn.guidance_task_status = TaskStatus.COMPLETED
        await db.commit()


@with_db_session
async def update_completed_turn_and_session(
    db: AsyncSession, session_id: str, turn_id: str
) -> None:
    turn = await db.get(Turn, turn_id)
    session = await db.get(ConversationSession, session_id)
    if turn:
        turn.status = TurnStatus.COMPLETED
        turn.completed_at = utc_now()
    if session:
        session.last_active_at = utc_now()
    await db.commit()


@with_db_session
async def update_failed_turn_by_id(
    db: AsyncSession, turn_id: str, error: Exception
) -> None:
    turn = await db.get(Turn, turn_id)
    if turn:
        turn.status = TurnStatus.FAILED
        turn.assistant_task_status = TaskStatus.FAILED
        turn.error_code = type(error).__name__
        turn.error_message = str(error)[:2000]
        turn.completed_at = utc_now()
        await db.commit()


@with_db_session
async def update_cancelled_turn_by_id(db: AsyncSession, turn_id: str) -> None:
    turn = await db.get(Turn, turn_id)
    if turn:
        turn.status = TurnStatus.CANCELLED
        turn.completed_at = utc_now()
        await db.commit()


@with_db_session
async def update_turn_for_restart_by_id(db: AsyncSession, turn_id: str) -> None:
    turn = await db.get(Turn, turn_id)
    if turn:
        turn.status = TurnStatus.QUEUED
        turn.assistant_task_status = TaskStatus.PENDING
        turn.audio_task_status = TaskStatus.PENDING
        turn.translation_task_status = TaskStatus.PENDING
        turn.suggestions_task_status = TaskStatus.PENDING
        turn.guidance_task_status = TaskStatus.PENDING
        await db.commit()


@with_db_session
async def update_turn_task_status_by_id(
    db: AsyncSession, turn_id: str, field: str, status: TaskStatus
) -> None:
    turn = await db.get(Turn, turn_id)
    if turn:
        setattr(turn, field, status)
        await db.commit()


@with_db_session
async def select_summary_context_by_session_id(
    db: AsyncSession, session_id: str, trigger_turns: int, recent_turns: int
) -> tuple[str | None, list[Turn], int] | None:
    session = await db.get(ConversationSession, session_id)
    if not session:
        return None
    turns = list(
        (
            await db.scalars(
                select(Turn)
                .where(
                    Turn.session_id == session_id,
                    Turn.status == TurnStatus.COMPLETED,
                    Turn.turn_index > session.summary_until_turn_index,
                )
                .order_by(Turn.turn_index)
                .limit(trigger_turns)
            )
        ).all()
    )
    if len(turns) < trigger_turns:
        return None
    summarize = turns[:-recent_turns]
    if not summarize:
        return None
    for turn in summarize:
        db.expunge(turn)
    return session.conversation_summary, summarize, summarize[-1].turn_index


@with_db_session
async def update_session_summary_by_id(
    db: AsyncSession, session_id: str, summary: str, until_index: int
) -> None:
    session = await db.get(ConversationSession, session_id)
    if session:
        session.conversation_summary = summary
        session.summary_until_turn_index = until_index
        await db.commit()


@with_db_session
async def select_retry_context_by_turn_id(
    db: AsyncSession, turn_id: str
) -> tuple[ConversationSession, Turn]:
    turn = await db.get(Turn, turn_id)
    if not turn:
        raise ValueError(f"Turn {turn_id} does not exist")
    session = await db.get(ConversationSession, turn.session_id)
    if not session or not turn.assistant_text:
        raise ValueError("Turn has no assistant response to retry")
    db.expunge(turn)
    db.expunge(session)
    return session, turn
