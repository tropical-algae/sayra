from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sayra.common.datetime import utc_now
from sayra.common.decorators import with_db_session
from sayra.core.db.models import EventRecord


@with_db_session
async def insert_event(
    db: AsyncSession,
    turn_id: str,
    event_type: str,
    data: dict,
    after_sequence: int = 0,
) -> int:
    latest = await db.scalar(
        select(EventRecord.sequence)
        .where(EventRecord.turn_id == turn_id)
        .order_by(EventRecord.sequence.desc())
        .limit(1)
    )
    sequence = max(int(latest or 0), after_sequence) + 1
    db.add(
        EventRecord(
            turn_id=turn_id,
            sequence=sequence,
            event_type=event_type,
            data=data,
            created_at=utc_now(),
        )
    )
    await db.commit()
    return sequence


@with_db_session
async def select_next_event_sequence_by_turn_id(
    db: AsyncSession, turn_id: str, after_sequence: int = 0
) -> int:
    latest = await db.scalar(
        select(EventRecord.sequence)
        .where(EventRecord.turn_id == turn_id)
        .order_by(EventRecord.sequence.desc())
        .limit(1)
    )
    return max(int(latest or 0), after_sequence) + 1


@with_db_session
async def select_events_by_turn_id_after_sequence(
    db: AsyncSession, turn_id: str, sequence: int, limit: int
) -> Sequence[EventRecord]:
    return (
        await db.scalars(
            select(EventRecord)
            .where(
                EventRecord.turn_id == turn_id,
                EventRecord.sequence > sequence,
            )
            .order_by(EventRecord.sequence)
            .limit(limit)
        )
    ).all()
