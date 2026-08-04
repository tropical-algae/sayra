from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from sayra.core.db.crud import turn as turn_crud
from sayra.core.db.models import Trace, Turn
from sayra.core.enums import AuxiliaryTask
from sayra.core.workflow.runtime import WorkflowRuntime


async def get_turn(db: AsyncSession, session_id: str, turn_id: str) -> Turn:
    return await turn_crud.select_turn_by_session_and_id(db, session_id, turn_id)


async def list_turns(
    db: AsyncSession, session_id: str, offset: int, limit: int
) -> tuple[Sequence[Turn], int]:
    return await turn_crud.select_turns_by_session_id(db, session_id, offset, limit)


async def list_traces(db: AsyncSession, turn_id: str) -> Sequence[Trace]:
    return await turn_crud.select_traces_by_turn_id(db, turn_id)


async def submit_turn(
    db: AsyncSession,
    runtime: WorkflowRuntime,
    session_id: str,
    submitted_text: str,
    turn_id: str | None = None,
    client_request_id: str | None = None,
) -> Turn:
    turn, should_start = await turn_crud.insert_or_update_turn_submission(
        db, session_id, submitted_text, turn_id, client_request_id
    )
    if should_start:
        runtime.start(turn.id)
    return turn


async def retry_auxiliary(
    db: AsyncSession,
    runtime: WorkflowRuntime,
    turn_id: str,
    task: AuxiliaryTask,
) -> Turn:
    turn = await turn_crud.update_turn_for_auxiliary_retry_by_id(db, turn_id, task)
    runtime.start_retry(turn_id, task)
    return turn
