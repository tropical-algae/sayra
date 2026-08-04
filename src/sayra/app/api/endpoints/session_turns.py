from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile, status

from sayra.app.api.deps import Container, DbSession
from sayra.app.schemas.turn import (
    TranscriptResponse,
    TurnListResponse,
    TurnResponse,
    TurnSubmit,
)
from sayra.app.services import transcription_service, turn_service
from sayra.common.config import settings

router = APIRouter()


@router.get("/{session_id}/turns", response_model=TurnListResponse)
async def list_turns(
    session_id: str,
    db: DbSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=settings.API_MAX_PAGE_SIZE)] = (
        settings.API_DEFAULT_PAGE_SIZE
    ),
):
    items, total = await turn_service.list_turns(db, session_id, offset, limit)
    return TurnListResponse(items=list(items), total=total)


@router.get("/{session_id}/turns/{turn_id}", response_model=TurnResponse)
async def get_turn(session_id: str, turn_id: str, db: DbSession):
    return await turn_service.get_turn(db, session_id, turn_id)


@router.post(
    "/{session_id}/turns/transcribe",
    response_model=TranscriptResponse,
    status_code=status.HTTP_201_CREATED,
)
async def transcribe_turn(
    session_id: str,
    db: DbSession,
    container: Container,
    audio: Annotated[UploadFile, File(description="Complete user recording")],
):
    content = await audio.read(container.config.MAX_UPLOAD_BYTES + 1)
    turn, transcript, auto_submitted = await transcription_service.transcribe_turn(
        db,
        container,
        session_id=session_id,
        audio=content,
        content_type=audio.content_type or "application/octet-stream",
        filename=audio.filename,
    )
    return TranscriptResponse(
        turn=TurnResponse.model_validate(turn),
        transcript=transcript,
        auto_submitted=auto_submitted,
    )


@router.post("/{session_id}/turns/{turn_id}/submit", response_model=TurnResponse)
async def submit_turn(
    session_id: str,
    turn_id: str,
    data: TurnSubmit,
    db: DbSession,
    container: Container,
):
    return await turn_service.submit_turn(
        db,
        container.runtime,
        session_id,
        data.submitted_text,
        turn_id,
        data.client_request_id,
    )
