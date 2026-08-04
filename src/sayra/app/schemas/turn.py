from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from sayra.app.schemas.audio import AudioAssetResponse
from sayra.core.enums import TaskStatus, TraceStatus, TraceStep, TurnStatus


class SuggestedReplyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sort_order: int
    target_text: str
    native_text: str
    audio_asset_id: str | None


class TurnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_index: int
    client_request_id: str | None
    status: TurnStatus
    raw_transcript: str | None
    refined_transcript: str | None
    submitted_text: str | None
    assistant_text: str | None
    assistant_translation: str | None
    guidance_original: str | None
    guidance_corrected: str | None
    guidance_explanation: str | None
    assistant_task_status: TaskStatus
    audio_task_status: TaskStatus
    translation_task_status: TaskStatus
    suggestions_task_status: TaskStatus
    guidance_task_status: TaskStatus
    error_code: str | None
    error_message: str | None
    trace_id: str | None
    submitted_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    suggestions: list[SuggestedReplyResponse] = Field(default_factory=list)
    audio_assets: list[AudioAssetResponse] = Field(default_factory=list)


class TranscriptResponse(BaseModel):
    turn: TurnResponse
    transcript: str
    auto_submitted: bool


class TurnSubmit(BaseModel):
    submitted_text: str = Field(min_length=1, max_length=10_000)
    client_request_id: str | None = Field(default=None, min_length=1, max_length=128)


class TurnListResponse(BaseModel):
    items: list[TurnResponse]
    total: int


class TraceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_id: str | None
    step: TraceStep
    status: TraceStatus
    provider: str | None
    provider_request_id: str | None
    attempt: int
    error_code: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
