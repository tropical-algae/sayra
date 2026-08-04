import asyncio
import base64
import json

import httpx

from sayra.common.config import Settings
from sayra.common.identifiers import IdType, new_id
from sayra.core.enums import Language
from sayra.core.exceptions import ProviderError
from sayra.core.types import AudioInput, TranscriptResult


class VolcengineASRProvider:
    """Volcengine big-model flash recording recognition adapter."""

    def __init__(self, config: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self._owns_client = client is None
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.config.VOLCENGINE_TIMEOUT_SECONDS
            )
        return self._client

    async def transcribe(self, audio: AudioInput, language: Language) -> TranscriptResult:
        client = self._get_client()
        request_id = new_id(IdType.REQUEST)
        url = self.config.VOLCENGINE_ASR_URL
        if not url:
            raise ProviderError("VOLCENGINE_ASR_URL is not configured")
        token = self.config.VOLCENGINE_ACCESS_TOKEN.get_secret_value()
        if not self.config.VOLCENGINE_APP_ID or not token:
            raise ProviderError("Volcengine ASR credentials are not configured")

        headers = {
            "X-Api-App-Key": self.config.VOLCENGINE_APP_ID,
            "X-Api-Access-Key": token,
            "X-Api-Resource-Id": self.config.VOLCENGINE_ASR_RESOURCE_ID,
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": "-1",
            "Content-Type": "application/json",
        }
        request_data: dict[str, object] = {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
        }
        provider_language = self.config.VOLCENGINE_ASR_LANGUAGE_MAP.get(language.value)
        if provider_language:
            request_data["language"] = provider_language

        def serialize_request() -> str:
            encoded_audio = base64.b64encode(audio.content).decode("ascii")
            payload = {
                "user": {"uid": request_id},
                "audio": {"data": encoded_audio},
                "request": request_data,
            }
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        # Recordings can be tens of MB. Perform both CPU-heavy serialization
        # steps in one thread handoff instead of blocking the event loop twice.
        body = await asyncio.to_thread(serialize_request)

        for attempt in range(self.config.VOLCENGINE_MAX_RETRIES + 1):
            response, retry_error = await self._post_once(client, url, headers, body)
            if retry_error:
                if attempt >= self.config.VOLCENGINE_MAX_RETRIES:
                    raise ProviderError(
                        f"Volcengine ASR request failed after retries: {retry_error}"
                    ) from retry_error
                await asyncio.sleep(
                    self.config.PROVIDER_RETRY_BACKOFF_SECONDS * (2**attempt)
                )
                continue
            if response is None:
                raise ProviderError("Volcengine ASR returned no response")
            status_code = response.headers.get("X-Api-Status-Code")
            if response.is_error or (status_code and status_code != "20000000"):
                detail = response.headers.get("X-Api-Message", response.text[:500])
                raise ProviderError(f"Volcengine ASR failed: {detail}")
            response_body = response.json()
            text = str(response_body.get("result", {}).get("text", "")).strip()
            if not text:
                raise ProviderError("Volcengine ASR returned an empty transcript")
            return TranscriptResult(
                text=text,
                provider_request_id=response.headers.get("X-Tt-Logid", request_id),
                metadata={"audio_info": response_body.get("audio_info", {})},
            )
        raise ProviderError("Volcengine ASR retry loop exhausted")

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    async def _post_once(
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        body: str,
    ) -> tuple[httpx.Response | None, httpx.HTTPError | None]:
        try:
            response = await client.post(url, headers=headers, content=body)
        except httpx.TransportError as exc:
            return None, exc
        status_code = response.headers.get("X-Api-Status-Code")
        if response.status_code >= 500 or (status_code and status_code.startswith("5")):
            return None, httpx.HTTPStatusError(
                "retryable Volcengine ASR response",
                request=response.request,
                response=response,
            )
        return response, None
