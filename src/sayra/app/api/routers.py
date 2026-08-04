from fastapi import APIRouter

from sayra.app.api.endpoints import audio, health, session_turns, sessions, turns
from sayra.app.api.websocket import conversation

router = APIRouter(prefix="/v1")
router.include_router(health.router, prefix="/system", tags=["system"])
router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
router.include_router(session_turns.router, prefix="/sessions", tags=["sessions-turns"])
router.include_router(turns.router, prefix="/turns", tags=["turns"])
router.include_router(audio.router, prefix="/audio", tags=["audio"])
router.include_router(conversation.router, prefix="/sessions", tags=["conversation"])
