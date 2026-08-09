from collections.abc import Sequence

from loguru import logger

from sayra.core.db.crud import turn as turn_crud
from sayra.core.db.models import Trace, Turn
from sayra.core.enums import AuxiliaryTask, RetryableAuxiliaryTask
from sayra.core.workflow.workflow import ConversationWorkflow


async def get_turn(session_id: str, turn_id: str) -> Turn:
    return await turn_crud.select_turn_by_session_and_id(session_id, turn_id)


async def list_turns(
    session_id: str, offset: int, limit: int
) -> tuple[Sequence[Turn], int]:
    return await turn_crud.select_turns_by_session_id(session_id, offset, limit)


async def list_traces(turn_id: str) -> Sequence[Trace]:
    return await turn_crud.select_traces_by_turn_id(turn_id)


async def submit_turn(
    workflow: ConversationWorkflow,
    session_id: str,
    submitted_text: str,
    turn_id: str | None = None,
    client_request_id: str | None = None,
) -> Turn:
    turn, should_start = await turn_crud.insert_or_update_turn_submission(
        session_id, submitted_text, turn_id, client_request_id
    )
    if should_start:
        workflow.start(turn.id)
    return turn


async def retry_auxiliary(
    workflow: ConversationWorkflow,
    turn_id: str,
    task: RetryableAuxiliaryTask,
) -> Turn:
    auxiliary_task = AuxiliaryTask(task.value)
    turn = await turn_crud.update_turn_for_auxiliary_retry_by_id(turn_id, auxiliary_task)
    workflow.start_retry(turn_id, auxiliary_task)
    return turn


async def generate_suggestions(
    workflow: ConversationWorkflow,
    turn_id: str,
    regenerate: bool,
) -> Turn:
    (
        turn,
        should_start,
        stale_paths,
    ) = await turn_crud.update_turn_for_suggestion_generation_by_id(turn_id, regenerate)
    for file_path in stale_paths:
        try:
            await workflow.storage.delete(file_path)
        except Exception as exc:  # noqa: PERF203
            logger.warning(
                "Failed to remove stale suggestion audio {}: {}", file_path, exc
            )
    if should_start:
        workflow.start_suggestions(turn_id)
    return turn
