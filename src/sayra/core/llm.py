from collections.abc import AsyncIterator
from typing import cast

from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletionChunk

from sayra.common.config import Settings
from sayra.core.exceptions import ProviderError


class OpenAICompatibleLLM:
    def __init__(self, config: Settings) -> None:
        self.config = config
        self._client_instance: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        api_key = self.config.LLM_API_KEY.get_secret_value()
        if not api_key:
            raise ProviderError("LLM_API_KEY is not configured")
        if self._client_instance is None:
            self._client_instance = AsyncOpenAI(
                api_key=api_key,
                base_url=self.config.LLM_BASE_URL,
                timeout=self.config.LLM_TIMEOUT_SECONDS,
                max_retries=self.config.LLM_MAX_RETRIES,
            )
        return self._client_instance

    async def stream_reply(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self.config.LLM_MODEL,
                messages=messages,  # type: ignore[arg-type]
                temperature=self.config.LLM_TEMPERATURE,
                stream=True,
            )
            stream = cast(AsyncStream[ChatCompletionChunk], response)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"LLM streaming request failed: {exc}") from exc

    async def complete(self, messages: list[dict[str, str]]) -> str:
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self.config.LLM_MODEL,
                messages=messages,  # type: ignore[arg-type]
                temperature=self.config.LLM_TEMPERATURE,
            )
            if not response.choices:
                raise ProviderError("LLM returned a response without choices")
            return response.choices[0].message.content or ""
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"LLM request failed: {exc}") from exc

    async def close(self) -> None:
        if self._client_instance is not None:
            await self._client_instance.close()
            self._client_instance = None
