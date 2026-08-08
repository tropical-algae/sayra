from loguru import logger

from sayra.common.datetime import utc_now
from sayra.common.identifiers import IdType, new_id
from sayra.core.db.crud import audio as audio_crud
from sayra.core.db.models import AudioAsset
from sayra.core.enums import AudioAssetStatus, AudioAssetType
from sayra.core.exceptions import ProviderError, SayraError
from sayra.core.types import FileStorage, SpeechRequest, TTSProvider


async def get_audio(audio_id: str) -> AudioAsset:
    return await audio_crud.select_ready_audio_by_id(audio_id)


async def generate_suggestion_audio(
    storage: FileStorage,
    tts: TTSProvider,
    turn_id: str,
    suggestion_id: str,
) -> AudioAsset:
    (
        suggestion,
        turn,
        session,
        audio_asset,
    ) = await audio_crud.select_suggestion_audio_context_by_ids(turn_id, suggestion_id)
    if audio_asset:
        return audio_asset
    if session is None:
        raise SayraError("Suggestion audio context is missing its session")
    chunks = [
        chunk.data
        async for chunk in tts.synthesize(
            SpeechRequest(
                text=suggestion.target_text,
                language=session.target_language,
                voice_id=session.voice_id,
                difficulty=session.difficulty_level,
            )
        )
    ]
    if not chunks:
        raise ProviderError("TTS returned no suggestion audio")

    file_path = f"sessions/{session.id}/turns/{turn.id}/suggestions/{suggestion.id}.mp3"
    stored = await storage.put(file_path, b"".join(chunks), "audio/mpeg")
    audio = AudioAsset(
        id=new_id(IdType.AUDIO_ASSET),
        session_id=session.id,
        turn_id=turn.id,
        asset_type=AudioAssetType.SUGGESTED_REPLY,
        file_path=stored.file_path,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        status=AudioAssetStatus.READY,
        checksum_sha256=stored.checksum_sha256,
        created_at=utc_now(),
    )
    try:
        return await audio_crud.insert_suggestion_audio(suggestion_id, audio)
    except Exception:
        try:
            await storage.delete(stored.file_path)
        except Exception as cleanup_error:
            logger.warning(
                "Failed to compensate suggestion audio {}: {}",
                stored.file_path,
                cleanup_error,
            )
        raise
