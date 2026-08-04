from sayra.common.config import Settings
from sayra.core.storage.local import LocalFileStorage
from sayra.core.storage.minio import MinioFileStorage
from sayra.core.types import FileStorage


def create_storage(config: Settings) -> FileStorage:
    """Create exactly one storage capability from application configuration."""

    if config.STORAGE_TYPE == "local":
        return LocalFileStorage(
            config.STORAGE_ROOT_PATH, config.STORAGE_STREAM_CHUNK_BYTES
        )
    if config.STORAGE_TYPE == "minio":
        return MinioFileStorage(
            endpoint=config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY.get_secret_value(),
            secret_key=config.MINIO_SECRET_KEY.get_secret_value(),
            bucket=config.STORAGE_BUCKET,
            root_path=config.STORAGE_ROOT_PATH,
            secure=config.MINIO_SECURE,
            region=config.MINIO_REGION,
            chunk_bytes=config.STORAGE_STREAM_CHUNK_BYTES,
        )
    raise ValueError(f"Unsupported storage type: {config.STORAGE_TYPE}")
