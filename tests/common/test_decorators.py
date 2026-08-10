import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from sayra.common.decorators import traced
from sayra.core.enums import TraceStep
from sayra.core.workflow import tracing


def test_traced_runs_method_inside_trace(monkeypatch) -> None:
    traced_ids: list[tuple[str, str]] = []

    @asynccontextmanager
    async def track_trace(session_id, turn_id, _step, _provider=None):
        traced_ids.append((session_id, turn_id))
        yield "trace-1"

    monkeypatch.setattr(tracing, "track_trace", track_trace)

    class Example:
        @traced(TraceStep.CONVERSATION)
        async def execute(self, session, turn, value: str) -> str:
            return f"{session.id}:{turn.id}:{value}"

    result = asyncio.run(
        Example().execute(
            SimpleNamespace(id="session-1"),
            SimpleNamespace(id="turn-1"),
            "completed",
        )
    )

    assert result == "session-1:turn-1:completed"
    assert traced_ids == [("session-1", "turn-1")]


def test_traced_resolves_provider_from_instance(monkeypatch) -> None:
    providers: list[str | None] = []

    @asynccontextmanager
    async def track_trace(_session_id, _turn_id, _step, provider=None):
        providers.append(provider)
        yield "trace-1"

    monkeypatch.setattr(tracing, "track_trace", track_trace)

    class Example:
        def __init__(self) -> None:
            self.config = SimpleNamespace(LLM_PROVIDER_NAME="configured-llm")

        @traced(
            TraceStep.CONVERSATION,
            provider=lambda self: self.config.LLM_PROVIDER_NAME,
        )
        async def execute(self, session, turn) -> None:
            _ = session, turn

    example = Example()
    asyncio.run(
        example.execute(
            SimpleNamespace(id="session-1"),
            SimpleNamespace(id="turn-1"),
        )
    )

    assert providers == ["configured-llm"]
