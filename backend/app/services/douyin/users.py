from __future__ import annotations

import asyncio
from typing import Any

from f2.apps.douyin.crawler import DouyinCrawler
from f2.apps.douyin.model import UserPost, UserProfile

from backend.app.services.douyin.client import build_douyin_headers, crawler_kwargs
from backend.app.services.douyin.helpers import (
    first_url,
    format_time,
    validate_sec_user_id,
)
from backend.app.services.media import MediaRegistry, MediaResource
from backend.app.services.session import LoginCookieStore


DEFAULT_POST_COUNT = 12


def _pagination(
    response: dict[str, Any], current_cursor: int | None = None
) -> dict[str, Any]:
    has_more = bool(response.get("has_more"))
    cursor = response.get("max_cursor")
    try:
        next_cursor = int(cursor) if has_more and cursor is not None else None
    except (TypeError, ValueError):
        next_cursor = None
    can_advance = next_cursor is not None and next_cursor != current_cursor
    return {
        "has_more": has_more and can_advance,
        "next_cursor": next_cursor,
    }


def _serialize_posts(
    post_items: list[dict[str, Any]],
    fallback_user: dict[str, Any],
    headers: dict[str, str],
    media_registry: MediaRegistry,
) -> list[dict[str, Any]]:
    resources: list[MediaResource] = []
    posts: list[dict[str, Any]] = []
    for item in post_items:
        video = item.get("video") or {}
        author = item.get("author") or {}
        cover_url = first_url(video.get("cover") or video.get("origin_cover"))
        cover_index = None
        if cover_url:
            resources.append(MediaResource(cover_url, headers, "image"))
            cover_index = len(resources) - 1
        posts.append(
            {
                "aweme_id": str(item.get("aweme_id") or ""),
                "description": item.get("desc") or "（无作品描述）",
                "created_at": format_time(item.get("create_time")),
                "duration_ms": item.get("duration") or video.get("duration"),
                "author": {
                    "nickname": author.get("nickname")
                    or fallback_user.get("nickname")
                    or "未知作者",
                    "unique_id": author.get("unique_id")
                    or fallback_user.get("unique_id")
                    or "",
                },
                "statistics": {
                    "likes": (item.get("statistics") or {}).get("digg_count"),
                    "comments": (item.get("statistics") or {}).get("comment_count"),
                },
                "cover_index": cover_index,
                "douyin_url": (
                    f"https://www.douyin.com/video/{item.get('aweme_id')}"
                    if item.get("aweme_id")
                    else None
                ),
            }
        )

    session_id = media_registry.add(resources)
    for post in posts:
        cover_index = post.pop("cover_index")
        if cover_index is not None:
            post["cover"] = {
                "label": "作品封面",
                "proxy_url": f"/api/media/{session_id}/{cover_index}",
            }
    return posts


async def _request_user_posts(
    sec_user_id: str,
    max_cursor: int,
    count: int,
    headers: dict[str, str],
) -> dict[str, Any]:
    async with DouyinCrawler(crawler_kwargs(headers)) as crawler:
        result = await crawler.fetch_user_post(
            UserPost(
                max_cursor=max_cursor,
                count=count,
                sec_user_id=sec_user_id,
            )
        )
    if result.get("status_code") not in (None, 0):
        raise RuntimeError(str(result.get("status_msg") or "作品接口请求失败"))
    return result


async def fetch_user_posts_page(
    sec_user_id: str,
    max_cursor: int,
    count: int,
    cookie_store: LoginCookieStore,
    media_registry: MediaRegistry,
) -> dict[str, Any]:
    """Fetch one cursor-based page of a user's public posts."""
    sec_user_id = validate_sec_user_id(sec_user_id)
    if max_cursor < 0:
        raise ValueError("作品游标格式不正确")
    if not 1 <= count <= 20:
        raise ValueError("每页作品数量必须在 1 到 20 之间")
    active_cookie = cookie_store.get()
    headers = build_douyin_headers(active_cookie)
    result = await _request_user_posts(sec_user_id, max_cursor, count, headers)
    return {
        "access_mode": "login_cookie" if active_cookie else "visitor",
        "posts": _serialize_posts(
            result.get("aweme_list") or [], {}, headers, media_registry
        ),
        "pagination": _pagination(result, max_cursor),
    }


async def fetch_user_inspector(
    sec_user_id: str,
    cookie_store: LoginCookieStore,
    media_registry: MediaRegistry,
) -> dict[str, Any]:
    """Fetch a public user profile and the first page of recent posts."""
    sec_user_id = validate_sec_user_id(sec_user_id)
    active_cookie = cookie_store.get()
    headers = build_douyin_headers(active_cookie)
    kwargs = crawler_kwargs(headers)

    async def request(method_name: str, params: Any) -> dict[str, Any]:
        async with DouyinCrawler(kwargs) as crawler:
            return await getattr(crawler, method_name)(params)

    profile_result, posts_result = await asyncio.gather(
        request("fetch_user_profile", UserProfile(sec_user_id=sec_user_id)),
        _request_user_posts(sec_user_id, 0, DEFAULT_POST_COUNT, headers),
        return_exceptions=True,
    )
    if isinstance(profile_result, Exception):
        raise RuntimeError(
            f"用户资料接口请求失败：{profile_result}"
        ) from profile_result
    user = profile_result.get("user") or {}
    if not user:
        raise RuntimeError(
            str(profile_result.get("status_msg") or "用户资料接口没有返回公开信息")
        )

    resources: list[MediaResource] = []

    def register(source_url: str | None, kind: str) -> int | None:
        if not source_url:
            return None
        resources.append(MediaResource(source_url, headers, kind))
        return len(resources) - 1

    avatar_index = register(
        first_url(
            user.get("avatar_larger")
            or user.get("avatar_medium")
            or user.get("avatar_thumb")
        ),
        "image",
    )
    posts_error = None
    if isinstance(posts_result, Exception):
        posts_error = str(posts_result)
        post_items = []
    else:
        post_items = posts_result.get("aweme_list") or []
        if posts_result.get("status_code") not in (None, 0):
            posts_error = str(posts_result.get("status_msg") or "作品接口请求失败")

    session_id = media_registry.add(resources)
    posts = _serialize_posts(post_items, user, headers, media_registry)

    return {
        "access_mode": "login_cookie" if active_cookie else "visitor",
        "profile": {
            "nickname": user.get("nickname") or "未知用户",
            "unique_id": user.get("unique_id") or "",
            "sec_user_id": user.get("sec_uid") or sec_user_id,
            "uid": str(user.get("uid") or ""),
            "signature": user.get("signature") or "",
            "follower_count": user.get("follower_count"),
            "following_count": user.get("following_count"),
            "total_favorited": user.get("total_favorited"),
            "aweme_count": user.get("aweme_count"),
            "favoriting_count": user.get("favoriting_count"),
            "mix_count": user.get("mix_count"),
            "ip_location": user.get("ip_location"),
            "city": user.get("city"),
            "country": user.get("country"),
            "gender": user.get("gender"),
            "user_age": user.get("user_age"),
            "live_status": user.get("live_status"),
            "is_ban": user.get("is_ban"),
            "profile_url": f"https://www.douyin.com/user/{sec_user_id}",
            "avatar": (
                {
                    "label": "用户头像",
                    "proxy_url": f"/api/media/{session_id}/{avatar_index}",
                }
                if avatar_index is not None
                else None
            ),
        },
        "posts": posts,
        "posts_error": posts_error,
        "pagination": (
            _pagination(posts_result, 0)
            if not isinstance(posts_result, Exception)
            else {"has_more": False, "next_cursor": None}
        ),
    }
