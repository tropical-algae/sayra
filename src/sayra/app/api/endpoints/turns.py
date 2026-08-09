from fastapi import APIRouter, status

from sayra.app.api.deps import Container
from sayra.app.schemas.audio import AudioAssetResponse
from sayra.app.schemas.turn import SuggestionGenerate, TraceResponse, TurnResponse
from sayra.app.services import audio_service, turn_service
from sayra.core.enums import RetryableAuxiliaryTask

router = APIRouter()


@router.post(
    "/{turn_id}/retry/{task}",
    response_model=TurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_auxiliary_task(
    turn_id: str, task: RetryableAuxiliaryTask, container: Container
):
    return await turn_service.retry_auxiliary(container.workflow, turn_id, task)


@router.get("/{turn_id}/traces", response_model=list[TraceResponse])
async def list_turn_traces(turn_id: str):
    return await turn_service.list_traces(turn_id)


@router.post(
    "/{turn_id}/suggestions",
    response_model=TurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_suggestions(
    turn_id: str,
    data: SuggestionGenerate,
    container: Container,
):
    return await turn_service.generate_suggestions(
        container.workflow, turn_id, data.regenerate
    )


@router.post(
    "/{turn_id}/suggestions/{suggestion_id}/audio",
    response_model=AudioAssetResponse,
)
async def generate_suggestion_audio(
    turn_id: str, suggestion_id: str, container: Container
):
    return await audio_service.generate_suggestion_audio(
        container.storage, container.tts, turn_id, suggestion_id
    )
