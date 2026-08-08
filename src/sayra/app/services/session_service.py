from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from loguru import logger

from sayra.app.schemas.session import SessionCreate
from sayra.core.db.crud import session as session_crud
from sayra.core.db.models import ConversationSession
from sayra.core.types import FileStorage

if TYPE_CHECKING:
    from sayra.app.container import AppContainer


async def create_session(data: SessionCreate) -> ConversationSession:
    return await session_crud.insert_session(data.model_dump())


async def get_session(session_id: str) -> ConversationSession:
    return await session_crud.select_session_by_id(session_id)


async def list_sessions(
    offset: int, limit: int
) -> tuple[Sequence[ConversationSession], int]:
    return await session_crud.select_sessions_page(offset, limit)


async def delete_session(storage: FileStorage, session_id: str) -> None:
    file_paths = await session_crud.update_session_for_deletion_by_id(session_id)
    try:
        for file_path in file_paths:
            await storage.delete(file_path)
    except Exception:
        await session_crud.update_session_deletion_result_by_id(session_id, failed=True)
        raise
    await session_crud.update_session_deletion_result_by_id(session_id, failed=False)


async def retry_failed_session_deletions(container: AppContainer) -> None:
    session_ids = await session_crud.select_failed_session_deletion_ids()
    for session_id in session_ids:
        try:
            await delete_session(container.storage, session_id)
        except Exception as exc:  # noqa: PERF203
            logger.warning(
                "Failed to resume deletion for session {}: {}", session_id, exc
            )
