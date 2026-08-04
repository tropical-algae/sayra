from datetime import datetime

from pydantic import BaseModel, ConfigDict

from sayra.core.enums import AudioAssetStatus, AudioAssetType


class AudioAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_id: str | None
    asset_type: AudioAssetType
    content_type: str
    duration_ms: int | None
    size_bytes: int
    status: AudioAssetStatus
    created_at: datetime
