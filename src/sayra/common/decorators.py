from __future__ import annotations

from collections.abc import Callable, Coroutine
from functools import wraps
from typing import TYPE_CHECKING, Any, Concatenate, ParamSpec, Protocol, TypeVar, cast

if TYPE_CHECKING:
    from sayra.core.db.models import ConversationSession, Turn
    from sayra.core.enums import TraceStep

P = ParamSpec("P")
R = TypeVar("R")
ProviderResolver = Callable[[Any], str | None]


class TraceContext(Protocol):
    def track(
        self,
        session_id: str,
        turn_id: str | None,
        step: TraceStep,
        provider: str | None = None,
    ) -> Any: ...


def traced(
    step: TraceStep,
    provider: str | ProviderResolver | None = None,
) -> Callable[
    [
        Callable[
            Concatenate[Any, ConversationSession, Turn, P],
            Coroutine[Any, Any, R],
        ]
    ],
    Callable[
        Concatenate[Any, ConversationSession, Turn, P],
        Coroutine[Any, Any, R],
    ],
]:
    """Trace an async instance method when its owner provides ``self.traces``.

    The decorated method must receive ``session`` and ``turn`` immediately after
    ``self``. Provider resolver functions are evaluated against the owning instance
    at call time, so injected settings remain effective.
    """

    def decorator(
        method: Callable[
            Concatenate[Any, ConversationSession, Turn, P],
            Coroutine[Any, Any, R],
        ],
    ) -> Callable[
        Concatenate[Any, ConversationSession, Turn, P],
        Coroutine[Any, Any, R],
    ]:
        @wraps(method)
        async def wrapper(
            self: Any,
            session: ConversationSession,
            turn: Turn,
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> R:
            traces = cast(TraceContext | None, getattr(self, "traces", None))
            if traces is None:
                return await method(self, session, turn, *args, **kwargs)

            resolved_provider = provider(self) if callable(provider) else provider

            async with traces.track(
                session.id,
                turn.id,
                step,
                resolved_provider,
            ):
                return await method(self, session, turn, *args, **kwargs)

        return wrapper

    return decorator
