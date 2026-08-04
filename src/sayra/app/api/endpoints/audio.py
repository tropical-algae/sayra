from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from sayra.app.api.deps import Container, DbSession
from sayra.app.services import audio_service

router = APIRouter()


@router.get("/{audio_id}")
async def get_audio(audio_id: str, db: DbSession, container: Container):
    asset = await audio_service.get_audio(db, audio_id)
    return StreamingResponse(
        container.storage.stream(asset.file_path), media_type=asset.content_type
    )
