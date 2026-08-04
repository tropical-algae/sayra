from fastapi import APIRouter, status

from sayra.app.api.deps import Container, DbSession
from sayra.app.schemas.audio import AudioAssetResponse
from sayra.app.schemas.turn import TraceResponse, TurnResponse
from sayra.app.services import audio_service, turn_service
from sayra.core.enums import AuxiliaryTask

router = APIRouter()


@router.post(
    "/{turn_id}/retry/{task}",
    response_model=TurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_auxiliary_task(
    turn_id: str, task: AuxiliaryTask, db: DbSession, container: Container
):
    return await turn_service.retry_auxiliary(db, container.runtime, turn_id, task)


@router.get("/{turn_id}/traces", response_model=list[TraceResponse])
async def list_turn_traces(turn_id: str, db: DbSession):
    return await turn_service.list_traces(db, turn_id)


@router.post(
    "/{turn_id}/suggestions/{suggestion_id}/audio",
    response_model=AudioAssetResponse,
)
async def generate_suggestion_audio(
    turn_id: str, suggestion_id: str, db: DbSession, container: Container
):
    return await audio_service.generate_suggestion_audio(
        db, container.storage, container.tts, turn_id, suggestion_id
    )
