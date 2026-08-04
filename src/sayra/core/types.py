from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from sayra.core.enums import DifficultyLevel, Language


@dataclass(frozen=True, slots=True)
class AudioInput:
    content: bytes
    content_type: str
    filename: str | None = None


@dataclass(frozen=True, slots=True)
class TranscriptResult:
    text: str
    provider_request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SpeechRequest:
    text: str
    language: Language
    voice_id: str
    difficulty: DifficultyLevel


@dataclass(frozen=True, slots=True)
class AudioChunk:
    data: bytes
    sequence: int
    content_type: str
    provider_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class StoredFile:
    """Provider-neutral metadata returned after storing one file."""

    file_path: str
    size_bytes: int
    content_type: str
    checksum_sha256: str | None = None


class ASRProvider(Protocol):
    async def transcribe(
        self, audio: AudioInput, language: Language
    ) -> TranscriptResult: ...


class AudioNormalizer(Protocol):
    async def normalize(self, audio: AudioInput) -> AudioInput: ...


class TTSProvider(Protocol):
    def synthesize(self, request: SpeechRequest) -> AsyncIterator[AudioChunk]: ...


class LLMProvider(Protocol):
    def stream_reply(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...

    async def complete(self, messages: list[dict[str, str]]) -> str: ...


class FileStorage(Protocol):
    async def initialize(self) -> None: ...

    async def put(self, file_path: str, data: bytes, content_type: str) -> StoredFile: ...

    def stream(self, file_path: str) -> AsyncIterator[bytes]: ...

    async def delete(self, file_path: str) -> None: ...
