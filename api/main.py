from fastapi import FastAPI

from config import settings
from api.health import router as health_router
from api.meetings import router as meetings_router


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Meetly meeting intelligence API.",
)


app.include_router(health_router)
app.include_router(meetings_router)

@app.get(
    "/",
    tags=["Root"],
)
async def root() -> dict[str, str]:
    return {
        "success": "true",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "running",
        "docs": "/docs",
    }


__all__ = [
    "app",
]