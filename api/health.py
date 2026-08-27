from fastapi import APIRouter

from meeting_bot.config import settings


router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("/")
async def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


__all__ = [
    "router",
]