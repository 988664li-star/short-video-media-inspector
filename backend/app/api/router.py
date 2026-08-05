from fastapi import APIRouter

from backend.app.api.routes import (
    capabilities,
    health,
    media,
    resolve,
    session,
    transcription,
    users,
)


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(session.router, prefix="/session", tags=["session"])
api_router.include_router(resolve.router, tags=["resolve"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(
    capabilities.router,
    prefix="/capabilities",
    tags=["capabilities"],
)
api_router.include_router(media.router, prefix="/media", tags=["media"])
api_router.include_router(transcription.router, tags=["transcription"])
