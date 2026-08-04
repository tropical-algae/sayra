import asyncio
import gzip
import json
import struct
from collections.abc import AsyncIterator

import websockets

from sayra.common.config import Settings
from sayra.common.identifiers import IdType, new_id
from sayra.core.exceptions import ProviderError
from sayra.core.types import AudioChunk, SpeechRequest

_FULL_CLIENT_REQUEST = bytes((0x11, 0x10, 0x11, 0x00))
_AUDIO_RESPONSE = 0xB
_ERROR_RESPONSE = 0xF


class VolcengineTTSProvider:
    """Volcengine WebSocket streaming TTS adapter.

    The endpoint is configured explicitly so deployments can select the enabled
    Volcengine TTS product without embedding tenant-specific URLs in code.
    """

    def __init__(self, config: Settings) -> None:
        self.config = config

    async def synthesize(self, request: SpeechRequest) -> AsyncIterator[AudioChunk]:
        url = self.config.VOLCENGINE_TTS_URL
        token = self.config.VOLCENGINE_ACCESS_TOKEN.get_secret_value()
        if not url:
            raise ProviderError("VOLCENGINE_TTS_URL is not configured")
        if not self.config.VOLCENGINE_APP_ID or not token:
            raise ProviderError("Volcengine TTS credentials are not configured")

        headers = {"Authorization": f"Bearer; {token}"}

        for attempt in range(self.config.VOLCENGINE_MAX_RETRIES + 1):
            yielded_audio = False
            request_id = new_id(IdType.REQUEST)
            payload = self._make_payload(request, request_id)
            compressed = gzip.compress(json.dumps(payload).encode("utf-8"))
            message = (
                _FULL_CLIENT_REQUEST + struct.pack(">I", len(compressed)) + compressed
            )
            try:
                async with websockets.connect(
                    url,
                    additional_headers=headers,
                    open_timeout=self.config.VOLCENGINE_TIMEOUT_SECONDS,
                    close_timeout=self.config.VOLCENGINE_TIMEOUT_SECONDS,
                    max_size=None,
                ) as socket:
                    await socket.send(message)
                    sequence = 0
                    async for response in socket:
                        if not isinstance(response, bytes):
                            continue
                        parsed = self._parse_response(response)
                        if parsed is None:
                            continue
                        audio, is_final = parsed
                        if audio:
                            yielded_audio = True
                            sequence += 1
                            yield AudioChunk(
                                data=audio,
                                sequence=sequence,
                                content_type="audio/mpeg",
                                provider_request_id=request_id,
                            )
                        if is_final:
                            return
                    if yielded_audio:
                        return
                    raise ProviderError("Volcengine TTS closed without audio")
            except Exception as exc:
                if yielded_audio or attempt >= self.config.VOLCENGINE_MAX_RETRIES:
                    if isinstance(exc, ProviderError):
                        raise
                    raise ProviderError(
                        f"Volcengine TTS request failed after retries: {exc}"
                    ) from exc
                await asyncio.sleep(
                    self.config.PROVIDER_RETRY_BACKOFF_SECONDS * (2**attempt)
                )

    def _make_payload(self, request: SpeechRequest, request_id: str) -> dict:
        speed = self.config.TTS_SPEED_BY_DIFFICULTY.get(request.difficulty.value, 1.0)
        return {
            "app": {
                "appid": self.config.VOLCENGINE_APP_ID,
                "token": self.config.VOLCENGINE_ACCESS_TOKEN.get_secret_value(),
                "cluster": self.config.VOLCENGINE_TTS_CLUSTER,
            },
            "user": {"uid": request_id},
            "audio": {
                "voice_type": request.voice_id,
                "encoding": "mp3",
                "speed_ratio": speed,
            },
            "request": {
                "reqid": request_id,
                "text": request.text,
                "text_type": "plain",
                "operation": "submit",
            },
        }

    @staticmethod
    def _parse_response(message: bytes) -> tuple[bytes, bool] | None:
        if len(message) < 4:
            raise ProviderError("Volcengine TTS returned a malformed frame")
        header_size = (message[0] & 0x0F) * 4
        message_type = message[1] >> 4
        flags = message[1] & 0x0F
        compression = message[2] & 0x0F
        payload = message[header_size:]

        if message_type == _AUDIO_RESPONSE:
            if flags == 0:
                return None
            if len(payload) < 8:
                raise ProviderError("Volcengine TTS returned a malformed audio frame")
            sequence, payload_size = struct.unpack(">iI", payload[:8])
            audio = payload[8 : 8 + payload_size]
            return audio, sequence < 0

        if message_type == _ERROR_RESPONSE:
            if len(payload) < 8:
                raise ProviderError("Volcengine TTS returned an unspecified error")
            code, payload_size = struct.unpack(">II", payload[:8])
            error_payload = payload[8 : 8 + payload_size]
            if compression == 1:
                error_payload = gzip.decompress(error_payload)
            raise ProviderError(
                f"Volcengine TTS error {code}: {error_payload.decode('utf-8', 'replace')}"
            )
        return None
