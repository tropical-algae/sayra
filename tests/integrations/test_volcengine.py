import json
import struct

import httpx
import pytest

from sayra.common.config import Settings
from sayra.core.enums import DifficultyLevel, Language
from sayra.core.speech.asr import VolcengineASRProvider
from sayra.core.speech.tts import VolcengineTTSProvider
from sayra.core.types import AudioInput, SpeechRequest


@pytest.mark.anyio
async def test_volcengine_asr_builds_flash_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.headers["X-Api-Resource-Id"] == "volc.bigasr.auc_turbo"
        assert body["audio"]["data"] == "YXVkaW8="
        assert body["request"]["language"] == "en-US"
        return httpx.Response(
            200,
            headers={"X-Api-Status-Code": "20000000", "X-Tt-Logid": "log-id"},
            json={"result": {"text": "hello"}, "audio_info": {"duration": 10}},
        )

    config = Settings(
        VOLCENGINE_APP_ID="app",
        VOLCENGINE_ACCESS_TOKEN="token",
        VOLCENGINE_ASR_URL="https://example.test/asr",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VolcengineASRProvider(config, client)
        result = await provider.transcribe(
            AudioInput(b"audio", "audio/webm"), Language.ENGLISH
        )
    assert result.text == "hello"
    assert result.provider_request_id == "log-id"


def test_volcengine_tts_parses_audio_and_error_frames() -> None:
    audio = b"mp3-data"
    message = bytes((0x11, 0xB1, 0x00, 0x00)) + struct.pack(">iI", -1, len(audio)) + audio
    assert VolcengineTTSProvider._parse_response(message) == (audio, True)

    provider = VolcengineTTSProvider(Settings())
    payload = provider._make_payload(
        SpeechRequest("hello", Language.ENGLISH, "voice", DifficultyLevel.A1),
        "request-id",
    )
    assert payload["audio"]["speed_ratio"] == 0.92
