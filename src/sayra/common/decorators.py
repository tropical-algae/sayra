from __future__ import annotations

from collections.abc import Callable, Coroutine
from functools import wraps
from typing import TYPE_CHECKING, Any, Concatenate, ParamSpec, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from sayra.core.db.models import ConversationSession, Turn
    from sayra.core.enums import TraceStep

P = ParamSpec("P")
R = TypeVar("R")
ProviderResolver = Callable[[Any], str | None]


def with_db_session(
    operation: Callable[
        Concatenate[AsyncSession, P],
        Coroutine[Any, Any, R],
    ],
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Run a CRUD operation with a short-lived local database session."""

    @wraps(operation)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        from sayra.core.db.session import LocalSession

        async with LocalSession() as db:
            return await operation(db, *args, **kwargs)

    return wrapper


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
    """Persist the execution trace of an async instance method.

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
            from sayra.core.workflow.tracing import track_trace

            resolved_provider = provider(self) if callable(provider) else provider

            async with track_trace(
                session.id,
                turn.id,
                step,
                resolved_provider,
            ):
                return await method(self, session, turn, *args, **kwargs)

        return wrapper

    return decorator
