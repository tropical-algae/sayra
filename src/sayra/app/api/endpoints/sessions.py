from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from sayra.app.api.deps import Container, DbSession
from sayra.app.schemas.session import SessionCreate, SessionListResponse, SessionResponse
from sayra.app.services import session_service
from sayra.common.config import settings

router = APIRouter()


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(data: SessionCreate, db: DbSession):
    return await session_service.create_session(db, data)


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    db: DbSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=settings.API_MAX_PAGE_SIZE)] = (
        settings.API_DEFAULT_PAGE_SIZE
    ),
):
    items, total = await session_service.list_sessions(db, offset, limit)
    return SessionListResponse(items=list(items), total=total)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: DbSession):
    return await session_service.get_session(db, session_id)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str, db: DbSession, container: Container
) -> Response:
    await session_service.delete_session(db, container.storage, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
