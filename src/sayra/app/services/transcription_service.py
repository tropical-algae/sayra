from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from sayra.common.datetime import utc_now
from sayra.common.identifiers import IdType, new_id
from sayra.core.db.crud import transcription as transcription_crud
from sayra.core.db.models import AudioAsset, Turn
from sayra.core.enums import AudioAssetStatus, AudioAssetType, TraceStep
from sayra.core.exceptions import BadRequestError, PayloadTooLargeError
from sayra.core.types import AudioInput
from sayra.core.workflow.tracing import track_trace, update_trace

if TYPE_CHECKING:
    from sayra.app.container import AppContainer


async def transcribe_turn(
    container: AppContainer,
    session_id: str,
    audio: bytes,
    content_type: str,
    filename: str | None,
) -> tuple[Turn, str, bool]:
    if not audio:
        raise BadRequestError("Uploaded audio is empty")
    if len(audio) > container.config.MAX_UPLOAD_BYTES:
        raise PayloadTooLargeError("Uploaded audio exceeds MAX_UPLOAD_BYTES")

    turn_id = new_id(IdType.TURN)
    session = await transcription_crud.insert_transcription_turn(session_id, turn_id)
    file_path = f"sessions/{session_id}/turns/{turn_id}/user.wav"
    stored = None
    recording_persisted = False
    try:
        async with track_trace(
            session_id,
            turn_id,
            TraceStep.TRANSCRIPTION,
            container.config.ASR_PROVIDER_NAME,
        ) as trace_id:
            normalized = await container.audio_normalizer.normalize(
                AudioInput(content=audio, content_type=content_type, filename=filename)
            )
            stored = await container.storage.put(
                file_path,
                normalized.content,
                normalized.content_type,
            )
            asset = AudioAsset(
                id=new_id(IdType.AUDIO_ASSET),
                session_id=session_id,
                turn_id=turn_id,
                asset_type=AudioAssetType.USER_RECORDING,
                file_path=stored.file_path,
                content_type=stored.content_type,
                size_bytes=stored.size_bytes,
                status=AudioAssetStatus.READY,
                checksum_sha256=stored.checksum_sha256,
                created_at=utc_now(),
            )
            await transcription_crud.insert_recording_asset(asset)
            recording_persisted = True
            result = await container.asr.transcribe(normalized, session.target_language)
            await update_trace(
                trace_id,
                provider_request_id=result.provider_request_id,
                metadata=result.metadata,
            )

        refined = None
        if session.transcript_refinement_enabled:
            try:
                async with track_trace(
                    session_id,
                    turn_id,
                    TraceStep.REFINEMENT,
                    container.config.LLM_PROVIDER_NAME,
                ):
                    refined = await container.llm.complete(
                        container.prompts.refinement(session, result.text)
                    )
                    refined = refined.strip()
            except Exception as exc:
                logger.warning(
                    "Transcript refinement failed for turn {}; using raw ASR: {}",
                    turn_id,
                    exc,
                )

        transcript = refined or result.text
        turn = await transcription_crud.update_transcription_result_by_turn_id(
            turn_id,
            result.text,
            refined,
            transcript,
            session.transcript_auto_submit,
        )
        if session.transcript_auto_submit:
            container.workflow.start(turn_id)
        return turn, transcript, session.transcript_auto_submit
    except Exception as exc:
        if stored and not recording_persisted:
            try:
                await container.storage.delete(stored.file_path)
            except Exception as cleanup_error:
                logger.warning(
                    "Failed to compensate recording {}: {}",
                    stored.file_path,
                    cleanup_error,
                )
        await transcription_crud.update_failed_transcription_by_turn_id(turn_id, exc)
        raise
