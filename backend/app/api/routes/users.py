from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_cookie_store, get_media_registry
from backend.app.schemas.requests import UserPostsRequest, UserProfileRequest
from backend.app.services.douyin.users import fetch_user_inspector, fetch_user_posts_page
from backend.app.services.media import MediaRegistry
from backend.app.services.session import LoginCookieStore


router = APIRouter()


@router.post("/user-profile")
async def user_profile(
    request: UserProfileRequest,
    cookie_store: Annotated[LoginCookieStore, Depends(get_cookie_store)],
    media_registry: Annotated[MediaRegistry, Depends(get_media_registry)],
) -> dict[str, Any]:
    try:
        return await fetch_user_inspector(
            request.sec_user_id,
            cookie_store,
            media_registry,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"用户资料获取失败：{exc}",
        ) from exc


@router.post("/user-posts")
async def user_posts(
    request: UserPostsRequest,
    cookie_store: Annotated[LoginCookieStore, Depends(get_cookie_store)],
    media_registry: Annotated[MediaRegistry, Depends(get_media_registry)],
) -> dict[str, Any]:
    try:
        return await fetch_user_posts_page(
            request.sec_user_id,
            request.max_cursor,
            request.count,
            cookie_store,
            media_registry,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"用户作品获取失败：{exc}",
        ) from exc
