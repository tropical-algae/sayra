from enum import StrEnum
from uuid import uuid4


class IdType(StrEnum):
    SESSION = "session"
    TURN = "turn"
    AUDIO_ASSET = "audio"
    SUGGESTED_REPLY = "suggest"
    TRACE = "trace"
    REQUEST = "request"


def new_id(id_type: IdType | None = None) -> str:
    """Create a UUID identifier, optionally prefixed with its resource type."""

    identifier = str(uuid4())
    if id_type is None:
        return identifier
    return f"{id_type.value}_{identifier}"
