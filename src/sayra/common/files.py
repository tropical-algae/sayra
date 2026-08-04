import re
from pathlib import Path, PurePosixPath

_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]+")
_AUDIO_EXTENSIONS = frozenset({"webm", "wav", "mp3", "ogg", "opus"})


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_component(value: str, fallback: str = "file") -> str:
    cleaned = _SAFE_COMPONENT.sub("-", value.strip()).strip(".-")
    return cleaned or fallback


def audio_extension(filename: str | None) -> str:
    if not filename or "." not in filename:
        return "webm"
    extension = safe_component(filename.rsplit(".", 1)[-1].lower(), "bin")
    return extension if extension in _AUDIO_EXTENSIONS else "bin"


def normalize_relative_path(value: str) -> str:
    """Normalize and validate a provider-independent POSIX relative path."""

    path = PurePosixPath(value.replace("\\", "/"))
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"Unsafe relative file path: {value!r}")
    return path.as_posix()


def join_object_path(root: str, relative_path: str) -> str:
    """Join a MinIO prefix and a persisted relative path without filesystem rules."""

    relative = normalize_relative_path(relative_path)
    prefix = root.replace("\\", "/").strip("/.")
    return f"{prefix}/{relative}" if prefix else relative
