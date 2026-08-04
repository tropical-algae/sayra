from typing import Literal

from pydantic import BaseModel, Field

from sayra.core.workflow.events import ServerEvent


class ClientEvent(BaseModel):
    type: Literal["turn.submit", "turn.subscribe", "turn.cancel"]
    turn_id: str | None = None
    submitted_text: str | None = Field(default=None, max_length=10_000)
    client_request_id: str | None = Field(default=None, min_length=1, max_length=128)
    after_sequence: int = Field(default=0, ge=0)


__all__ = ["ClientEvent", "ServerEvent"]
