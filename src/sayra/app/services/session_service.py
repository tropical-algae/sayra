from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from sayra.app.schemas.session import SessionCreate
from sayra.core.db.crud import session as session_crud
from sayra.core.db.models import ConversationSession
from sayra.core.types import FileStorage

if TYPE_CHECKING:
    from sayra.app.container import AppContainer


async def create_session(db: AsyncSession, data: SessionCreate) -> ConversationSession:
    return await session_crud.insert_session(db, data.model_dump())


async def get_session(db: AsyncSession, session_id: str) -> ConversationSession:
    return await session_crud.select_session_by_id(db, session_id)


async def list_sessions(
    db: AsyncSession, offset: int, limit: int
) -> tuple[Sequence[ConversationSession], int]:
    return await session_crud.select_sessions_page(db, offset, limit)


async def delete_session(db: AsyncSession, storage: FileStorage, session_id: str) -> None:
    file_paths = await session_crud.update_session_for_deletion_by_id(db, session_id)
    try:
        for file_path in file_paths:
            await storage.delete(file_path)
    except Exception:
        await session_crud.update_session_deletion_result_by_id(
            db, session_id, failed=True
        )
        raise
    await session_crud.update_session_deletion_result_by_id(db, session_id, failed=False)


async def retry_failed_session_deletions(container: AppContainer) -> None:
    async with container.session_factory() as db:
        session_ids = await session_crud.select_failed_session_deletion_ids(db)
        for session_id in session_ids:
            try:
                await delete_session(db, container.storage, session_id)
            except Exception as exc:  # noqa: PERF203
                logger.warning(
                    "Failed to resume deletion for session {}: {}", session_id, exc
                )
