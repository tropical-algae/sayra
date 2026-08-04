import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from sayra.common.files import ensure_directory, normalize_relative_path
from sayra.common.hashing import sha256_hex
from sayra.core.exceptions import StorageError
from sayra.core.types import StoredFile


class LocalFileStorage:
    """Store files below one configured local root without blocking asyncio."""

    def __init__(self, root_path: str, chunk_bytes: int = 64 * 1024) -> None:
        self.root = Path(root_path).expanduser().resolve()
        self.chunk_bytes = chunk_bytes

    def _resolve(self, file_path: str) -> Path:
        relative = normalize_relative_path(file_path)
        resolved = (self.root / relative).resolve()
        if not resolved.is_relative_to(self.root):
            raise StorageError(f"File path escapes storage root: {file_path}")
        return resolved

    async def initialize(self) -> None:
        await asyncio.to_thread(ensure_directory, self.root)

    async def put(self, file_path: str, data: bytes, content_type: str) -> StoredFile:
        path = self._resolve(file_path)

        def write() -> str:
            ensure_directory(path.parent)
            path.write_bytes(data)
            return sha256_hex(data)

        try:
            checksum = await asyncio.to_thread(write)
        except OSError as exc:
            raise StorageError(f"Cannot store local file {file_path}: {exc}") from exc
        return StoredFile(file_path, len(data), content_type, checksum)

    async def stream(self, file_path: str) -> AsyncIterator[bytes]:
        path = self._resolve(file_path)
        try:
            file = await asyncio.to_thread(path.open, "rb")
        except OSError as exc:
            raise StorageError(f"Cannot open local file {file_path}: {exc}") from exc
        try:
            while chunk := await asyncio.to_thread(file.read, self.chunk_bytes):
                yield chunk
        finally:
            file.close()

    async def delete(self, file_path: str) -> None:
        path = self._resolve(file_path)
        try:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        except OSError as exc:
            raise StorageError(f"Cannot delete local file {file_path}: {exc}") from exc
