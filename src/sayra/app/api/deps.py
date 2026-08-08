from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from sayra.app.container import AppContainer


def get_container(connection: HTTPConnection) -> AppContainer:
    return connection.app.state.container


Container = Annotated[AppContainer, Depends(get_container)]
