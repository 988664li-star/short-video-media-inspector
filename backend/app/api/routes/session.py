from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_cookie_store, get_media_registry
from backend.app.schemas.requests import CookieRequest
from backend.app.services.media import MediaRegistry
from backend.app.services.session import LoginCookieStore


router = APIRouter()
CookieStoreDependency = Annotated[LoginCookieStore, Depends(get_cookie_store)]
MediaRegistryDependency = Annotated[MediaRegistry, Depends(get_media_registry)]


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
            "登录 Cookie 已保存到本机后端私有文件，重启后仍会载入"
            if session_status["has_login_markers"]
            else "Cookie 已载入，但未发现常见登录字段，请确认复制完整"
        ),
    }


@router.delete("/cookie")
async def clear_cookie(
    cookie_store: CookieStoreDependency,
    media_registry: MediaRegistryDependency,
) -> dict[str, Any]:
    try:
        cookie_store.clear()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    media_registry.clear()
    return {**cookie_store.status(), "message": "登录 Cookie 已从内存和本机文件清除"}
