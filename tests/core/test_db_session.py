import asyncio
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from sayra.common.decorators import with_db_session
from sayra.core.db import session as db_session


def test_with_db_session_injects_local_session(monkeypatch) -> None:
    injected = AsyncSession()

    @asynccontextmanager
    async def session_context():
        yield injected

    monkeypatch.setattr(db_session, "LocalSession", session_context)

    @with_db_session
    async def operation(db: AsyncSession, value: str) -> tuple[AsyncSession, str]:
        return db, value

    received, value = asyncio.run(operation("value"))

    assert received is injected
    assert value == "value"
    asyncio.run(injected.close())
