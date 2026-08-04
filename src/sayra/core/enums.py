from enum import StrEnum


class Language(StrEnum):
    SIMPLIFIED_CHINESE = "zh-CN"
    TRADITIONAL_CHINESE = "zh-TW"
    ENGLISH = "en"
    JAPANESE = "ja"
    KOREAN = "ko"
    FRENCH = "fr"
    GERMAN = "de"
    SPANISH = "es"


class DifficultyLevel(StrEnum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class ExamLevel(StrEnum):
    DEFAULT = "default"
    CET4 = "cet-4"
    CET6 = "cet-6"
    IELTS = "ielts"
    TOEFL = "toefl"


class ConversationMode(StrEnum):
    NATURAL = "natural"
    GUIDED = "guided"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    DELETING = "deleting"
    DELETE_FAILED = "delete_failed"


class TurnStatus(StrEnum):
    TRANSCRIBING = "transcribing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_TURN_STATUSES = (
    TurnStatus.TRANSCRIBING,
    TurnStatus.AWAITING_CONFIRMATION,
    TurnStatus.QUEUED,
    TurnStatus.PROCESSING,
)


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AuxiliaryTask(StrEnum):
    AUDIO = "audio"
    TRANSLATION = "translation"
    SUGGESTIONS = "suggestions"
    GUIDANCE = "guidance"


class AudioAssetType(StrEnum):
    USER_RECORDING = "user_recording"
    ASSISTANT_REPLY = "assistant_reply"
    OPENING_MESSAGE = "opening_message"
    SUGGESTED_REPLY = "suggested_reply"


class AudioAssetStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class TraceStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TraceStep(StrEnum):
    TRANSCRIPTION = "transcription"
    REFINEMENT = "refinement"
    CONVERSATION = "conversation"
    TTS = "tts"
    TRANSLATION = "translation"
    SUGGESTIONS = "suggestions"
    GUIDANCE = "guidance"
    SUMMARY = "summary"
    PERSISTENCE = "persistence"
