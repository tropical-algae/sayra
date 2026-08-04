from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sayra.common.config import settings
from sayra.common.files import ensure_directory
from sayra.core.db.base import Base

database_path = Path(settings.DATABASE_PATH).expanduser().resolve()
ensure_directory(database_path.parent)

local_engine = create_async_engine(
    url=f"sqlite+aiosqlite:///{database_path.as_posix()}",
    pool_pre_ping=True,
    echo=settings.DATABASE_ECHO,
)
LocalSession = async_sessionmaker(
    bind=local_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db_models(engine: AsyncEngine = local_engine) -> None:
    """Create database objects that are missing from the configured SQLite file."""

    # Importing models registers every mapped table on Base.metadata.
    from sayra.core.db import models as _models

    logger.info("Check SQL table structure and create the missing tables.")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


@event.listens_for(local_engine.sync_engine, "connect")
def configure_sqlite(connection: Any, _record: Any) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={settings.DATABASE_BUSY_TIMEOUT_MS}")
    cursor.close()
