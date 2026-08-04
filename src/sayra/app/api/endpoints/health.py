from fastapi import APIRouter

from sayra.common.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "version": settings.VERSION}
