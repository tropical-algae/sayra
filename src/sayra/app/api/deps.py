from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from sayra.app.container import AppContainer


def get_container(connection: HTTPConnection) -> AppContainer:
    return connection.app.state.container


Container = Annotated[AppContainer, Depends(get_container)]


async def get_db(container: Container) -> AsyncGenerator[AsyncSession]:
    async with container.session_factory() as db:
        yield db


DbSession = Annotated[AsyncSession, Depends(get_db)]
