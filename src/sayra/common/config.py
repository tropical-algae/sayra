from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sayra import __version__

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_ROOT = PACKAGE_ROOT / "core" / "prompts" / "templates"

# Prompt names and files are application configuration, not a second configuration
# system. Deployments may override PROMPT_ROOT while retaining this validated map.
PROMPT_FILES: dict[str, str] = {
    "conversation": "conversation.md",
    "mode_guided": "mode_guided.md",
    "mode_natural": "mode_natural.md",
    "refinement": "refinement.md",
    "translation": "translation.md",
    "suggestions": "suggestions.md",
    "guidance": "guidance.md",
    "summary": "summary.md",
    "summary_turn": "summary_turn.md",
}


class Settings(BaseSettings):
    """Single source of truth for runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "Sayra"
    VERSION: str = __version__
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = Field(default=8000, ge=1, le=65535)
    WORKERS: int = 1
    API_PREFIX: str = "/api"
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    API_DEFAULT_PAGE_SIZE: int = Field(default=20, ge=1)
    API_MAX_PAGE_SIZE: int = Field(default=100, ge=1)

    # SQLite is configured by its file path. The database layer alone translates
    # this into SQLAlchemy's internal driver URL.
    DATABASE_PATH: Path = Path("./data/sayra.db")
    DATABASE_ECHO: bool = False
    DATABASE_BUSY_TIMEOUT_MS: int = Field(default=5000, ge=0)

    # A persisted file_path is always relative. Providers resolve it as:
    # local:  STORAGE_ROOT_PATH / file_path
    # minio:  STORAGE_BUCKET / STORAGE_ROOT_PATH / file_path
    STORAGE_TYPE: Literal["local", "minio"] = "local"
    STORAGE_BUCKET: str = "sayra"
    STORAGE_ROOT_PATH: str = "./data/files"
    STORAGE_STREAM_CHUNK_BYTES: int = Field(default=64 * 1024, ge=1024)
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: SecretStr = SecretStr("minioadmin")
    MINIO_SECRET_KEY: SecretStr = SecretStr("minioadmin")
    MINIO_SECURE: bool = False
    MINIO_REGION: str | None = None
    STARTUP_CHECK_STORAGE: bool = True
    RETRY_FAILED_DELETIONS_ON_STARTUP: bool = True

    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: SecretStr = SecretStr("")
    LLM_MODEL: str = "gpt-5-mini"
    LLM_PROVIDER_NAME: str = "openai"
    LLM_TEMPERATURE: float = Field(default=0.7, ge=0, le=2)
    LLM_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0)
    LLM_MAX_RETRIES: int = Field(default=2, ge=0)
    PROMPT_ROOT: Path = DEFAULT_PROMPT_ROOT

    VOLCENGINE_APP_ID: str = ""
    VOLCENGINE_ACCESS_TOKEN: SecretStr = SecretStr("")
    VOLCENGINE_ASR_URL: str = (
        "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
    )
    VOLCENGINE_TTS_URL: str = "wss://openspeech.bytedance.com/api/v1/tts/ws_binary"
    VOLCENGINE_ASR_RESOURCE_ID: str = "volc.bigasr.auc_turbo"
    VOLCENGINE_TTS_CLUSTER: str = "volcano_tts"
    VOLCENGINE_ASR_LANGUAGE_MAP: dict[str, str] = Field(
        default_factory=lambda: {
            "zh-CN": "zh-CN",
            "zh-TW": "zh-TW",
            "en": "en-US",
            "ja": "ja-JP",
            "ko": "ko-KR",
            "fr": "fr-FR",
            "de": "de-DE",
            "es": "es-ES",
        }
    )
    TTS_SPEED_BY_DIFFICULTY: dict[str, float] = Field(
        default_factory=lambda: {
            "A1": 0.92,
            "A2": 0.95,
            "B1": 0.98,
            "B2": 1.0,
            "C1": 1.02,
            "C2": 1.04,
        }
    )
    VOLCENGINE_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    VOLCENGINE_MAX_RETRIES: int = Field(default=2, ge=0)
    PROVIDER_RETRY_BACKOFF_SECONDS: float = Field(default=0.25, ge=0)
    ASR_PROVIDER_NAME: str = "volcengine"
    TTS_PROVIDER_NAME: str = "volcengine"

    DEFAULT_VOICE_ID: str = "default"
    DEFAULT_SUGGESTION_COUNT: int = Field(default=1, ge=0)
    MAX_SUGGESTION_COUNT: int = Field(default=5, ge=0)
    MAX_UPLOAD_BYTES: int = Field(default=25 * 1024 * 1024, gt=0)
    AUDIO_CONVERSION_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    CONTEXT_RECENT_TURNS: int = Field(default=10, ge=1)
    CONTEXT_SUMMARY_TRIGGER_TURNS: int = Field(default=14, ge=2)
    TTS_SENTENCE_MIN_CHARS: int = Field(default=12, ge=1)
    TTS_SENTENCE_MAX_CHARS: int = Field(default=180, ge=1, le=10_000)
    LIVE_EVENT_BUFFER_SIZE: int = Field(default=512, ge=1)
    EVENT_REPLAY_BATCH_SIZE: int = Field(default=200, ge=1)
    LIVE_AUDIO_EVENT_RETENTION_SECONDS: float = Field(default=60.0, ge=0)
    TASK_SHUTDOWN_GRACE_SECONDS: float = Field(default=15.0, ge=0)

    LOG_ROOT: Path = Path("./log")
    LOG_LEVEL: str = "INFO"
    LOG_FILE_ENCODING: str = "utf-8"
    LOG_FILE_OUTPUT: bool = True

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("STORAGE_ROOT_PATH")
    @classmethod
    def validate_storage_root(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("STORAGE_ROOT_PATH must not be empty")
        return value.strip()

    @field_validator("WORKERS")
    @classmethod
    def require_single_worker(cls, value: int) -> int:
        if value != 1:
            raise ValueError("In-process runtime requires WORKERS must be 1")
        return value

    @model_validator(mode="after")
    def validate_runtime_policy(self) -> "Settings":
        if self.API_DEFAULT_PAGE_SIZE > self.API_MAX_PAGE_SIZE:
            raise ValueError("API_DEFAULT_PAGE_SIZE must not exceed API_MAX_PAGE_SIZE")
        if self.DEFAULT_SUGGESTION_COUNT > self.MAX_SUGGESTION_COUNT:
            raise ValueError(
                "DEFAULT_SUGGESTION_COUNT must not exceed MAX_SUGGESTION_COUNT"
            )
        if self.TTS_SENTENCE_MIN_CHARS > self.TTS_SENTENCE_MAX_CHARS:
            raise ValueError(
                "TTS_SENTENCE_MIN_CHARS must not exceed TTS_SENTENCE_MAX_CHARS"
            )
        if self.CONTEXT_SUMMARY_TRIGGER_TURNS <= self.CONTEXT_RECENT_TURNS:
            raise ValueError(
                "CONTEXT_SUMMARY_TRIGGER_TURNS must exceed CONTEXT_RECENT_TURNS"
            )
        if any(speed <= 0 for speed in self.TTS_SPEED_BY_DIFFICULTY.values()):
            raise ValueError("All TTS_SPEED_BY_DIFFICULTY values must be positive")
        if self.ENVIRONMENT.lower() != "production":
            return self

        missing: list[str] = []
        for name, value in {
            "LLM_API_KEY": self.LLM_API_KEY.get_secret_value(),
            "VOLCENGINE_ACCESS_TOKEN": self.VOLCENGINE_ACCESS_TOKEN.get_secret_value(),
        }.items():
            if not value:
                missing.append(name)
        if not self.VOLCENGINE_APP_ID:
            missing.append("VOLCENGINE_APP_ID")
        if not self.DEFAULT_VOICE_ID or self.DEFAULT_VOICE_ID == "default":
            missing.append("DEFAULT_VOICE_ID")
        if self.STORAGE_TYPE == "minio":
            for name, value in {
                "MINIO_ACCESS_KEY": self.MINIO_ACCESS_KEY.get_secret_value(),
                "MINIO_SECRET_KEY": self.MINIO_SECRET_KEY.get_secret_value(),
            }.items():
                if not value or value == "minioadmin":
                    missing.append(name)
        if missing:
            raise ValueError(
                f"Production configuration is missing or unsafe: {', '.join(missing)}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
