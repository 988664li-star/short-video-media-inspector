from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_cookie_store, get_media_registry
from backend.app.schemas.requests import ResolveRequest
from backend.app.services.douyin.resolver import resolve_share_text
from backend.app.services.media import MediaRegistry
from backend.app.services.platforms import resolve_platform, share_url_from_text
from backend.app.services.session import LoginCookieStore
from backend.app.services.tiktok.resolver import resolve_share_url as resolve_tiktok_share_url


router = APIRouter()


@router.post("/resolve")
async def resolve_media(
    request: ResolveRequest,
    cookie_store: Annotated[LoginCookieStore, Depends(get_cookie_store)],
    media_registry: Annotated[MediaRegistry, Depends(get_media_registry)],
) -> dict[str, Any]:
    try:
        share_url = share_url_from_text(request.share_text)
        platform = resolve_platform(share_url, request.platform)
        if platform == "tiktok":
            return await resolve_tiktok_share_url(share_url, media_registry)
        return await resolve_share_text(
            request.share_text,
            cookie_store,
            media_registry,
            direct_aweme_id=request.aweme_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"解析失败：{exc}",
        ) from exc
