from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sayra.core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from sayra.core.enums import (
    AudioAssetStatus,
    AudioAssetType,
    ConversationMode,
    DifficultyLevel,
    ExamLevel,
    Language,
    SessionStatus,
    TaskStatus,
    TraceStatus,
    TraceStep,
    TurnStatus,
)


def enum_column(enum_type: type, *, default: object | None = None):
    return mapped_column(
        Enum(
            enum_type,
            native_enum=False,
            validate_strings=True,
            values_callable=lambda members: [member.value for member in members],
        ),
        default=default,
        nullable=False,
    )


class ConversationSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sessions"

    native_language: Mapped[Language] = enum_column(Language)
    target_language: Mapped[Language] = enum_column(Language)
    difficulty_level: Mapped[DifficultyLevel] = enum_column(DifficultyLevel)
    exam_level: Mapped[ExamLevel] = enum_column(ExamLevel, default=ExamLevel.DEFAULT)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    conversation_mode: Mapped[ConversationMode] = enum_column(ConversationMode)
    suggestion_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    voice_id: Mapped[str] = mapped_column(String(128), nullable=False)
    transcript_refinement_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    transcript_auto_submit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    conversation_summary: Mapped[str | None] = mapped_column(Text)
    summary_until_turn_index: Mapped[int] = mapped_column(Integer, default=0)
    next_turn_index: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[SessionStatus] = enum_column(
        SessionStatus, default=SessionStatus.ACTIVE
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    turns: Mapped[list["Turn"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    audio_assets: Mapped[list["AudioAsset"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Turn(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "turns"
    __table_args__ = (
        UniqueConstraint("session_id", "turn_index", name="uq_turns_session_turn_index"),
        UniqueConstraint(
            "session_id", "client_request_id", name="uq_turns_session_client_request"
        ),
        Index("ix_turns_session_status", "session_id", "status"),
        Index(
            "uq_turns_one_active_per_session",
            "session_id",
            unique=True,
            sqlite_where=text(
                "status IN ('transcribing', 'awaiting_confirmation', 'queued', 'processing')"
            ),
        ),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    client_request_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[TurnStatus] = enum_column(TurnStatus)
    raw_transcript: Mapped[str | None] = mapped_column(Text)
    refined_transcript: Mapped[str | None] = mapped_column(Text)
    submitted_text: Mapped[str | None] = mapped_column(Text)
    assistant_text: Mapped[str | None] = mapped_column(Text)
    assistant_translation: Mapped[str | None] = mapped_column(Text)
    guidance_original: Mapped[str | None] = mapped_column(Text)
    guidance_corrected: Mapped[str | None] = mapped_column(Text)
    guidance_explanation: Mapped[str | None] = mapped_column(Text)
    assistant_task_status: Mapped[TaskStatus] = enum_column(
        TaskStatus, default=TaskStatus.PENDING
    )
    audio_task_status: Mapped[TaskStatus] = enum_column(
        TaskStatus, default=TaskStatus.PENDING
    )
    translation_task_status: Mapped[TaskStatus] = enum_column(
        TaskStatus, default=TaskStatus.PENDING
    )
    suggestions_task_status: Mapped[TaskStatus] = enum_column(
        TaskStatus, default=TaskStatus.PENDING
    )
    guidance_task_status: Mapped[TaskStatus] = enum_column(
        TaskStatus, default=TaskStatus.PENDING
    )
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[ConversationSession] = relationship(back_populates="turns")
    suggestions: Mapped[list["SuggestedReply"]] = relationship(
        back_populates="turn", cascade="all, delete-orphan"
    )
    audio_assets: Mapped[list["AudioAsset"]] = relationship(
        back_populates="turn", cascade="all, delete-orphan"
    )


class SuggestedReply(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "suggested_replies"
    __table_args__ = (
        UniqueConstraint(
            "turn_id", "sort_order", name="uq_suggested_replies_turn_sort_order"
        ),
    )

    turn_id: Mapped[str] = mapped_column(
        ForeignKey("turns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    native_text: Mapped[str] = mapped_column(Text, nullable=False)
    audio_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    turn: Mapped[Turn] = relationship(back_populates="suggestions")


class AudioAsset(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audio_assets"
    __table_args__ = (Index("ix_audio_assets_session_type", "session_id", "asset_type"),)

    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn_id: Mapped[str | None] = mapped_column(
        ForeignKey("turns.id", ondelete="CASCADE"), index=True
    )
    asset_type: Mapped[AudioAssetType] = enum_column(AudioAssetType)
    # Provider-neutral relative path. The configured storage implementation resolves
    # it against its own root (and bucket for MinIO).
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[AudioAssetStatus] = enum_column(AudioAssetStatus)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    session: Mapped[ConversationSession] = relationship(back_populates="audio_assets")
    turn: Mapped[Turn | None] = relationship(back_populates="audio_assets")


class Trace(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "traces"
    __table_args__ = (Index("ix_traces_turn_step", "turn_id", "step"),)

    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn_id: Mapped[str | None] = mapped_column(
        ForeignKey("turns.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[TraceStep] = enum_column(TraceStep)
    status: Mapped[TraceStatus] = enum_column(TraceStatus)
    provider: Mapped[str | None] = mapped_column(String(128))
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventRecord(Base):
    __tablename__ = "turn_events"

    turn_id: Mapped[str] = mapped_column(
        ForeignKey("turns.id", ondelete="CASCADE"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
