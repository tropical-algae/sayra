import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from openai import AsyncOpenAI

from sayra.common.config import Settings
from sayra.core.exceptions import ProviderError
from sayra.core.llm import OpenAICompatibleLLM


class FakeStream:
    def __init__(self, chunks: list[Any]) -> None:
        self.chunks = chunks

    async def __aiter__(self) -> AsyncIterator[Any]:
        for chunk in self.chunks:
            yield chunk


class FakeCompletions:
    def __init__(self, response: Any) -> None:
        self.response = response

    async def create(self, **_kwargs: Any) -> Any:
        return self.response


def make_provider(response: Any) -> OpenAICompatibleLLM:
    provider = OpenAICompatibleLLM(Settings(LLM_API_KEY="test"))
    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(response)))
    provider._client_instance = cast(AsyncOpenAI, client)
    return provider


def test_stream_reply_skips_chunks_without_choices() -> None:
    empty_chunk = SimpleNamespace(choices=[])
    content_chunk = SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello"))]
    )
    provider = make_provider(FakeStream([empty_chunk, content_chunk]))

    async def collect() -> list[str]:
        return [item async for item in provider.stream_reply([])]

    assert asyncio.run(collect()) == ["Hello"]


def test_complete_rejects_response_without_choices() -> None:
    provider = make_provider(SimpleNamespace(choices=[]))

    async def complete() -> None:
        await provider.complete([])

    with pytest.raises(ProviderError, match="without choices"):
        asyncio.run(complete())
