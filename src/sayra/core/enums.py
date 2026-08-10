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


class RetryableAuxiliaryTask(StrEnum):
    AUDIO = "audio"
    TRANSLATION = "translation"
    GUIDANCE = "guidance"


class ServerEventType(StrEnum):
    TURN_STARTED = "turn.started"
    TURN_COMPLETED = "turn.completed"
    TURN_FAILED = "turn.failed"
    TURN_CANCELLED = "turn.cancelled"
    TURN_INTERRUPTED = "turn.interrupted"
    TURN_AUXILIARY_RETRY_COMPLETED = "turn.auxiliary_retry.completed"
    TURN_AUXILIARY_COMPLETED = "turn.auxiliary.completed"
    TURN_AUXILIARY_FAILED = "turn.auxiliary.failed"

    ASSISTANT_TEXT_DELTA = "assistant.text.delta"
    ASSISTANT_TEXT_COMPLETED = "assistant.text.completed"
    ASSISTANT_AUDIO_STARTED = "assistant.audio.started"
    ASSISTANT_AUDIO_DELTA = "assistant.audio.delta"
    ASSISTANT_AUDIO_COMPLETED = "assistant.audio.completed"
    ASSISTANT_AUDIO_FAILED = "assistant.audio.failed"
    ASSISTANT_TRANSLATION_COMPLETED = "assistant.translation.completed"
    ASSISTANT_TRANSLATION_FAILED = "assistant.translation.failed"
    ASSISTANT_SUGGESTION_COMPLETED = "assistant.suggestion.completed"
    ASSISTANT_SUGGESTION_FAILED = "assistant.suggestion.failed"
    ASSISTANT_GUIDANCE_COMPLETED = "assistant.guidance.completed"
    ASSISTANT_GUIDANCE_FAILED = "assistant.guidance.failed"

    CONNECTION_HEARTBEAT = "connection.heartbeat"
    PROTOCOL_ERROR = "protocol.error"


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
