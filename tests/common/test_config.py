import pytest
from pydantic import ValidationError

from sayra.common.config import Settings


def test_production_rejects_placeholder_credentials() -> None:
    with pytest.raises(ValidationError, match="Production configuration is missing"):
        Settings(ENVIRONMENT="production", _env_file=None)


def test_production_accepts_explicit_safe_configuration() -> None:
    config = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        DATABASE_PATH="./data/production.db",
        LLM_API_KEY="llm-secret",
        VOLCENGINE_APP_ID="volc-app",
        VOLCENGINE_ACCESS_TOKEN="volc-token",
        DEFAULT_VOICE_ID="volc-voice",
    )

    assert config.ENVIRONMENT == "production"
    assert config.WORKERS == 1
    assert config.STORAGE_TYPE == "local"


def test_in_process_runtime_rejects_multiple_workers() -> None:
    with pytest.raises(ValidationError, match="WORKERS must be 1"):
        Settings(WORKERS=2, _env_file=None)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"LLM_TIMEOUT_SECONDS": 0}, "greater than 0"),
        (
            {"DEFAULT_SUGGESTION_COUNT": 2, "MAX_SUGGESTION_COUNT": 1},
            "DEFAULT_SUGGESTION_COUNT",
        ),
        (
            {"API_DEFAULT_PAGE_SIZE": 101, "API_MAX_PAGE_SIZE": 100},
            "API_DEFAULT_PAGE_SIZE",
        ),
        ({"TTS_SPEED_BY_DIFFICULTY": {"A1": 0}}, "must be positive"),
    ],
)
def test_invalid_runtime_policy_is_rejected(
    override: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(**override, _env_file=None)
