from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sayra.core.db.models import Turn
from sayra.core.enums import TaskStatus, TurnStatus


async def update_interrupted_tasks_and_select_recoverable_turn_ids(
    db: AsyncSession,
) -> Sequence[str]:
    fields = (
        Turn.audio_task_status,
        Turn.translation_task_status,
        Turn.suggestions_task_status,
        Turn.guidance_task_status,
    )
    for field in fields:
        await db.execute(
            update(Turn)
            .where(Turn.status == TurnStatus.COMPLETED, field == TaskStatus.RUNNING)
            .values({field.key: TaskStatus.FAILED})
        )
    await db.commit()
    return (
        await db.scalars(
            select(Turn.id).where(
                Turn.status.in_((TurnStatus.QUEUED, TurnStatus.PROCESSING))
            )
        )
    ).all()
