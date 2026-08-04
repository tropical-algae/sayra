from pathlib import Path

import pytest

from sayra.common.config import Settings
from sayra.core.storage.factory import create_storage
from sayra.core.storage.local import LocalFileStorage
from sayra.core.storage.minio import MinioFileStorage


@pytest.mark.anyio
async def test_local_storage_resolves_relative_file_path(tmp_path: Path) -> None:
    storage = LocalFileStorage(str(tmp_path / "files"))
    await storage.initialize()

    stored = await storage.put(
        "sessions/session-1/turns/turn-1/user.webm", b"audio", "audio/webm"
    )

    assert stored.file_path == "sessions/session-1/turns/turn-1/user.webm"
    assert (tmp_path / "files" / stored.file_path).read_bytes() == b"audio"
    assert (
        b"".join([chunk async for chunk in storage.stream(stored.file_path)]) == b"audio"
    )

    await storage.delete(stored.file_path)
    assert not (tmp_path / "files" / stored.file_path).exists()


@pytest.mark.anyio
async def test_local_storage_rejects_directory_escape(tmp_path: Path) -> None:
    storage = LocalFileStorage(str(tmp_path))
    with pytest.raises(ValueError, match="Unsafe relative file path"):
        await storage.put("../outside", b"data", "application/octet-stream")


def test_storage_factory_selects_configured_provider(tmp_path: Path) -> None:
    local = create_storage(
        Settings(STORAGE_TYPE="local", STORAGE_ROOT_PATH=str(tmp_path))
    )
    assert isinstance(local, LocalFileStorage)

    minio = create_storage(
        Settings(
            STORAGE_TYPE="minio",
            STORAGE_BUCKET="bucket",
            STORAGE_ROOT_PATH="audio/root",
        )
    )
    assert isinstance(minio, MinioFileStorage)
    assert minio._object_name("sessions/one/audio.mp3") == (
        "audio/root/sessions/one/audio.mp3"
    )
