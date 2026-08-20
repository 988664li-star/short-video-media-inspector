import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router
from backend.app.core.config import settings
from backend.app.dependencies import (
    cookie_store,
    media_registry,
    seedance_workspace_service,
    shot_detection_service,
    transcription_service,
)
from backend.app.services.session import remove_cookie_file


async def _privacy_cleanup_loop() -> None:
    interval = max(10, settings.privacy_cleanup_interval_seconds)
    while True:
        await asyncio.sleep(interval)
        await asyncio.to_thread(transcription_service.cleanup_expired_cache)
        await asyncio.to_thread(shot_detection_service.cleanup_expired_cache)
        media_registry.prune()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Remove data left behind by older versions before serving any request.
    await asyncio.to_thread(remove_cookie_file, settings.cookie_store_path)
    await asyncio.to_thread(transcription_service.clear_cache)
    await asyncio.to_thread(seedance_workspace_service.initialize)
    cleanup_task = asyncio.create_task(_privacy_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        media_registry.clear()
        cookie_store.clear()
        await asyncio.to_thread(transcription_service.clear_cache)


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version="2.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Range"],
        expose_headers=["Content-Length", "Content-Range", "Accept-Ranges"],
    )
    application.include_router(api_router, prefix=settings.api_prefix)
    return application


app = create_app()
