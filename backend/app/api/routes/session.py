import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import (
    get_cookie_store,
    get_media_registry,
    get_transcription_service,
)
from backend.app.schemas.requests import CookieRequest
from backend.app.services.media import MediaRegistry
from backend.app.services.session import LoginCookieStore
from backend.app.services.transcription import TranscriptionService


router = APIRouter()
CookieStoreDependency = Annotated[LoginCookieStore, Depends(get_cookie_store)]
MediaRegistryDependency = Annotated[MediaRegistry, Depends(get_media_registry)]
TranscriptionServiceDependency = Annotated[
    TranscriptionService, Depends(get_transcription_service)
]


@router.get("/status")
async def get_status(cookie_store: CookieStoreDependency) -> dict[str, Any]:
    return cookie_store.status()


@router.post("/cookie")
async def save_cookie(
    request: CookieRequest,
    cookie_store: CookieStoreDependency,
) -> dict[str, Any]:
    try:
        session_status = cookie_store.set(request.cookie)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    return {
        **session_status,
        "message": (
            "登录 Cookie 仅保存在当前服务内存，重启或清除登录态后会自动删除"
            if session_status["storage"] == "memory"
            else "登录 Cookie 已保存到本机后端私有文件，重启后仍会载入"
            if session_status["has_login_markers"]
            else "Cookie 已载入，但未发现常见登录字段，请确认复制完整"
        ),
    }


@router.delete("/cookie")
async def clear_cookie(
    cookie_store: CookieStoreDependency,
    media_registry: MediaRegistryDependency,
    transcription_service: TranscriptionServiceDependency,
) -> dict[str, Any]:
    try:
        cookie_store.clear()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    media_registry.clear()
    await asyncio.to_thread(transcription_service.clear_cache)
    return {
        **cookie_store.status(),
        "message": "登录 Cookie、媒体代理和临时文案缓存已清除",
    }
