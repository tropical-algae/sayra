import asyncio
import io
from collections.abc import AsyncIterator

from minio import Minio

from sayra.common.files import join_object_path, normalize_relative_path
from sayra.common.hashing import sha256_hex
from sayra.core.exceptions import StorageError
from sayra.core.types import StoredFile


class MinioFileStorage:
    """Resolve provider-neutral file paths under bucket/root in MinIO."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        root_path: str,
        secure: bool,
        region: str | None,
        chunk_bytes: int,
    ) -> None:
        self.bucket = bucket
        self.root_path = root_path
        self.chunk_bytes = chunk_bytes
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region,
        )

    def _object_name(self, file_path: str) -> str:
        return join_object_path(self.root_path, normalize_relative_path(file_path))

    async def initialize(self) -> None:
        def initialize_bucket() -> None:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)

        try:
            await asyncio.to_thread(initialize_bucket)
        except Exception as exc:
            raise StorageError(f"Cannot initialize MinIO bucket: {exc}") from exc

    async def put(self, file_path: str, data: bytes, content_type: str) -> StoredFile:
        relative = normalize_relative_path(file_path)
        object_name = self._object_name(relative)

        def upload() -> str:
            checksum = sha256_hex(data)
            self.client.put_object(
                self.bucket,
                object_name,
                io.BytesIO(data),
                len(data),
                content_type=content_type,
            )
            return checksum

        try:
            checksum = await asyncio.to_thread(upload)
        except Exception as exc:
            raise StorageError(f"Cannot store MinIO file {relative}: {exc}") from exc
        return StoredFile(relative, len(data), content_type, checksum)

    async def stream(self, file_path: str) -> AsyncIterator[bytes]:
        object_name = self._object_name(file_path)
        response = None
        try:
            response = await asyncio.to_thread(
                self.client.get_object, self.bucket, object_name
            )
            while chunk := await asyncio.to_thread(response.read, self.chunk_bytes):
                yield chunk
        except Exception as exc:
            raise StorageError(f"Cannot read MinIO file {file_path}: {exc}") from exc
        finally:
            if response is not None:

                def close_response() -> None:
                    response.close()
                    response.release_conn()

                await asyncio.to_thread(close_response)

    async def delete(self, file_path: str) -> None:
        try:
            await asyncio.to_thread(
                self.client.remove_object, self.bucket, self._object_name(file_path)
            )
        except Exception as exc:
            raise StorageError(f"Cannot delete MinIO file {file_path}: {exc}") from exc
