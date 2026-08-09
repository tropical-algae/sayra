from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sayra.common.config import settings
from sayra.core.enums import (
    ConversationMode,
    DifficultyLevel,
    ExamLevel,
    Language,
    SessionStatus,
)


class SessionCreate(BaseModel):
    native_language: Language
    target_language: Language
    difficulty_level: DifficultyLevel
    exam_level: ExamLevel = ExamLevel.DEFAULT
    topic: str = Field(min_length=1, max_length=500)
    conversation_mode: ConversationMode = ConversationMode.NATURAL
    suggestion_count: int = Field(
        default=settings.DEFAULT_SUGGESTION_COUNT,
        ge=0,
        le=settings.MAX_SUGGESTION_COUNT,
    )
    suggestions_auto_generate: bool = False
    voice_id: str = Field(default=settings.DEFAULT_VOICE_ID, min_length=1, max_length=128)
    transcript_refinement_enabled: bool = False
    transcript_auto_submit: bool = False

    @model_validator(mode="after")
    def validate_language_configuration(self) -> "SessionCreate":
        if self.native_language == self.target_language:
            raise ValueError("native_language and target_language must be different")
        if (
            self.exam_level != ExamLevel.DEFAULT
            and self.target_language != Language.ENGLISH
        ):
            raise ValueError("exam_level is currently supported only for English")
        if self.suggestions_auto_generate and self.suggestion_count == 0:
            raise ValueError(
                "suggestion_count must be greater than zero when automatic suggestions are enabled"
            )
        return self


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    native_language: Language
    target_language: Language
    difficulty_level: DifficultyLevel
    exam_level: ExamLevel
    topic: str
    conversation_mode: ConversationMode
    suggestion_count: int
    suggestions_auto_generate: bool
    voice_id: str
    transcript_refinement_enabled: bool
    transcript_auto_submit: bool
    conversation_summary: str | None
    summary_until_turn_index: int
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    last_active_at: datetime


class SessionListResponse(BaseModel):
    items: list[SessionResponse]
    total: int
