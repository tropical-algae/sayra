from sqlalchemy.ext.asyncio import AsyncSession

from sayra.common.decorators import with_db_session
from sayra.core.db.models import AudioAsset, ConversationSession, SuggestedReply, Turn
from sayra.core.enums import AudioAssetStatus, TurnStatus
from sayra.core.exceptions import InvalidStateError, NotFoundError


@with_db_session
async def select_ready_audio_by_id(db: AsyncSession, audio_id: str) -> AudioAsset:
    asset = await db.get(AudioAsset, audio_id)
    if not asset or asset.status != AudioAssetStatus.READY:
        raise NotFoundError(f"Audio asset {audio_id} is not available")
    return asset


@with_db_session
async def select_suggestion_audio_context_by_ids(
    db: AsyncSession, turn_id: str, suggestion_id: str
) -> tuple[SuggestedReply, Turn, ConversationSession | None, AudioAsset | None]:
    suggestion = await db.get(SuggestedReply, suggestion_id)
    turn = await db.get(Turn, turn_id)
    if not suggestion or suggestion.turn_id != turn_id or not turn:
        raise NotFoundError(f"Suggestion {suggestion_id} does not exist")
    if turn.status != TurnStatus.COMPLETED:
        raise InvalidStateError(
            "Suggestion audio is available only after the turn completes"
        )
    if suggestion.audio_asset_id:
        asset = await db.get(AudioAsset, suggestion.audio_asset_id)
        if asset and asset.status == AudioAssetStatus.READY:
            return suggestion, turn, None, asset
    session = await db.get(ConversationSession, turn.session_id)
    if not session:
        raise NotFoundError(f"Session {turn.session_id} does not exist")
    return suggestion, turn, session, None


@with_db_session
async def insert_suggestion_audio(
    db: AsyncSession, suggestion_id: str, audio: AudioAsset
) -> AudioAsset:
    suggestion = await db.get(SuggestedReply, suggestion_id)
    if not suggestion:
        raise NotFoundError(f"Suggestion {suggestion_id} does not exist")
    db.add(audio)
    suggestion.audio_asset_id = audio.id
    await db.commit()
    await db.refresh(audio)
    return audio
