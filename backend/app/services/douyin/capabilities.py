from __future__ import annotations

from typing import Any, Literal

from f2.apps.douyin.crawler import DouyinCrawler
from f2.apps.douyin.model import (
    FollowFeed,
    FollowingUserLive,
    FriendFeed,
    HomePostSearch,
    LiveImFetch,
    PostComment,
    PostCommentReply,
    PostFeed,
    PostRelated,
    QueryUser,
    SuggestWord,
    UserCollection,
    UserCollects,
    UserCollectsVideo,
    UserFollower,
    UserFollowing,
    UserLike,
    UserLive2,
    UserLiveStatus,
    UserMix,
    UserMusicCollection,
    UserPost,
)

from backend.app.services.douyin.catalog import MediaCatalog
from backend.app.services.douyin.client import build_douyin_headers, crawler_kwargs
from backend.app.services.douyin.helpers import (
    first_url,
    format_time,
    validate_sec_user_id,
)
from backend.app.services.douyin.resolver import summarize_aweme, summarize_comments
from backend.app.services.media import MediaRegistry
from backend.app.services.session import LoginCookieStore


class LoginRequiredError(RuntimeError):
    """Raised when an endpoint needs a real Douyin login session."""


def _access_mode(cookie: str) -> str:
    return "login_cookie" if cookie else "visitor"


def _require_login(cookie_store: LoginCookieStore) -> str:
    status = cookie_store.status()
    if not status.get("has_login_markers"):
        raise LoginRequiredError("此能力需要先粘贴包含 sessionid 的登录 Cookie")
    return cookie_store.get()


def _ensure_success(result: dict[str, Any], label: str) -> None:
    status_code = result.get("status_code")
    if status_code not in (None, 0):
        message = (
            result.get("status_msg") or result.get("message") or f"{label}请求失败"
        )
        raise RuntimeError(f"{message}（status_code={status_code}）")


async def _request(cookie: str, method: str, params: Any) -> dict[str, Any]:
    headers = build_douyin_headers(cookie)
    async with DouyinCrawler(crawler_kwargs(headers)) as crawler:
        result = await getattr(crawler, method)(params)
    if not isinstance(result, dict) or not result:
        raise RuntimeError("上游接口没有返回有效 JSON")
    _ensure_success(result, method)
    return result


def _pagination(
    result: dict[str, Any], current_cursor: int, item_count: int
) -> dict[str, Any]:
    has_more = bool(result.get("has_more"))
    candidate = next(
        (
            result.get(key)
            for key in ("max_cursor", "cursor", "offset")
            if result.get(key) is not None
        ),
        None,
    )
    try:
        next_cursor = (
            int(candidate) if candidate is not None else current_cursor + item_count
        )
    except (TypeError, ValueError):
        next_cursor = current_cursor + item_count
    if not has_more or next_cursor == current_cursor:
        next_cursor = None
    return {
        "has_more": bool(has_more and next_cursor is not None),
        "next_cursor": next_cursor,
    }


def _unwrap_awemes(items: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = raw.get("aweme") or raw.get("item") or raw
        if isinstance(item, dict) and item.get("aweme_id"):
            normalized.append(item)
    return normalized


def _user_summary(user: dict[str, Any], catalog: MediaCatalog) -> dict[str, Any]:
    return {
        "nickname": user.get("nickname") or user.get("short_id") or "未知用户",
        "unique_id": user.get("unique_id") or "",
        "sec_user_id": user.get("sec_uid") or user.get("sec_user_id") or "",
        "uid": str(user.get("uid") or user.get("user_id") or ""),
        "signature": user.get("signature") or "",
        "follower_count": user.get("follower_count"),
        "following_count": user.get("following_count"),
        "aweme_count": user.get("aweme_count"),
        "ip_location": user.get("ip_location"),
        "live_status": user.get("live_status"),
        "avatar": catalog.prepare(
            first_url(
                user.get("avatar_larger")
                or user.get("avatar_medium")
                or user.get("avatar_thumb")
            ),
            "image",
            "用户头像",
        ),
    }


def _post_payload(
    result: dict[str, Any], cookie: str, cursor: int, registry: MediaRegistry
) -> dict[str, Any]:
    catalog = MediaCatalog(build_douyin_headers(cookie))
    raw_items = result.get("aweme_list") or result.get("data") or []
    items = _unwrap_awemes(raw_items)
    payload = {
        "access_mode": _access_mode(cookie),
        "items": [summarize_aweme(item, catalog) for item in items],
        "pagination": _pagination(result, cursor, len(items)),
    }
    return catalog.commit(payload, registry)


async def fetch_comments_page(
    aweme_id: str,
    cursor: int,
    count: int,
    cookie_store: LoginCookieStore,
    registry: MediaRegistry,
) -> dict[str, Any]:
    cookie = cookie_store.get()
    result = await _request(
        cookie,
        "fetch_post_comment",
        PostComment(aweme_id=aweme_id, cursor=cursor, count=count),
    )
    catalog = MediaCatalog(build_douyin_headers(cookie))
    items = summarize_comments(result, catalog)
    return catalog.commit(
        {
            "access_mode": _access_mode(cookie),
            "items": items,
            "total": result.get("total"),
            "pagination": _pagination(result, cursor, len(items)),
        },
        registry,
    )


async def fetch_related_posts(
    aweme_id: str,
    count: int,
    cookie_store: LoginCookieStore,
    registry: MediaRegistry,
) -> dict[str, Any]:
    cookie = cookie_store.get()
    result = await _request(
        cookie,
        "fetch_post_related",
        PostRelated(aweme_id=aweme_id, count=count, filterGids=aweme_id),
    )
    payload = _post_payload(result, cookie, 0, registry)
    payload["pagination"] = {"has_more": False, "next_cursor": None}
    return payload


async def fetch_comment_replies(
    aweme_id: str,
    comment_id: str,
    cursor: int,
    count: int,
    cookie_store: LoginCookieStore,
    registry: MediaRegistry,
) -> dict[str, Any]:
    cookie = cookie_store.get()
    result = await _request(
        cookie,
        "fetch_post_comment_reply",
        PostCommentReply(
            item_id=aweme_id, comment_id=comment_id, cursor=cursor, count=count
        ),
    )
    catalog = MediaCatalog(build_douyin_headers(cookie))
    items = summarize_comments(result, catalog)
    return catalog.commit(
        {
            "access_mode": _access_mode(cookie),
            "items": items,
            "pagination": _pagination(result, cursor, len(items)),
        },
        registry,
    )


async def fetch_user_content(
    kind: Literal["posts", "likes", "mix"],
    sec_user_id: str | None,
    mix_id: str | None,
    cursor: int,
    count: int,
    cookie_store: LoginCookieStore,
    registry: MediaRegistry,
) -> dict[str, Any]:
    cookie = cookie_store.get()
    if kind == "posts":
        target = validate_sec_user_id(sec_user_id)
        method, params = "fetch_user_post", UserPost(
            max_cursor=cursor, count=count, sec_user_id=target
        )
    elif kind == "likes":
        target = validate_sec_user_id(sec_user_id)
        method, params = "fetch_user_like", UserLike(
            max_cursor=cursor, count=count, sec_user_id=target
        )
    else:
        method, params = "fetch_user_mix", UserMix(
            cursor=cursor, count=count, mix_id=str(mix_id)
        )
    result = await _request(cookie, method, params)
    return _post_payload(result, cookie, cursor, registry)


async def fetch_connections(
    kind: Literal["following", "followers"],
    sec_user_id: str,
    user_id: str,
    cursor: int,
    count: int,
    cookie_store: LoginCookieStore,
    registry: MediaRegistry,
) -> dict[str, Any]:
    cookie = _require_login(cookie_store)
    target = validate_sec_user_id(sec_user_id)
    if kind == "following":
        method, params, key = (
            "fetch_user_following",
            UserFollowing(
                sec_user_id=target, user_id=user_id, offset=cursor, count=count
            ),
            "followings",
        )
    else:
        method, params, key = (
            "fetch_user_follower",
            UserFollower(
                sec_user_id=target, user_id=user_id, offset=cursor, count=count
            ),
            "followers",
        )
    result = await _request(cookie, method, params)
    catalog = MediaCatalog(build_douyin_headers(cookie))
    raw_users = result.get(key) or []
    users = [
        _user_summary(user, catalog) for user in raw_users if isinstance(user, dict)
    ]
    return catalog.commit(
        {
            "access_mode": _access_mode(cookie),
            "items": users,
            "pagination": _pagination(result, cursor, len(users)),
        },
        registry,
    )


async def fetch_account_library(
    kind: Literal["collections", "folders", "folder_posts", "music"],
    cursor: int,
    count: int,
    folder_id: str | None,
    cookie_store: LoginCookieStore,
    registry: MediaRegistry,
) -> dict[str, Any]:
    cookie = _require_login(cookie_store)
    if kind == "collections":
        result = await _request(
            cookie, "fetch_user_collection", UserCollection(cursor=cursor, count=count)
        )
        return _post_payload(result, cookie, cursor, registry)
    if kind == "folder_posts":
        result = await _request(
            cookie,
            "fetch_user_collects_video",
            UserCollectsVideo(cursor=cursor, count=count, collects_id=str(folder_id)),
        )
        return _post_payload(result, cookie, cursor, registry)

    catalog = MediaCatalog(build_douyin_headers(cookie))
    if kind == "folders":
        result = await _request(
            cookie, "fetch_user_collects", UserCollects(cursor=cursor, count=count)
        )
        raw_items = result.get("collects_list") or []
        items = [
            {
                "id": str(item.get("collects_id") or item.get("id") or ""),
                "name": item.get("collects_name") or item.get("name") or "未命名收藏夹",
                "description": item.get("desc") or item.get("description") or "",
                "count": item.get("total_number")
                or item.get("aweme_count")
                or item.get("count"),
                "cover": catalog.prepare(
                    first_url(item.get("cover_url") or item.get("cover")),
                    "image",
                    "收藏夹封面",
                ),
            }
            for item in raw_items
            if isinstance(item, dict)
        ]
    else:
        result = await _request(
            cookie,
            "fetch_user_music_collection",
            UserMusicCollection(cursor=cursor, count=count),
        )
        raw_items = result.get("mc_list") or []
        items = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            item = raw.get("music") if isinstance(raw.get("music"), dict) else raw
            items.append(
                {
                    "id": str(item.get("id") or item.get("mid") or ""),
                    "title": item.get("title") or "未命名音乐",
                    "author": item.get("author") or item.get("owner_nickname") or "",
                    "duration_seconds": item.get("duration"),
                    "use_count": item.get("user_count"),
                    "cover": catalog.prepare(
                        first_url(
                            item.get("cover_large")
                            or item.get("cover_medium")
                            or item.get("cover_thumb")
                        ),
                        "image",
                        "音乐封面",
                    ),
                    "audio": catalog.prepare(
                        first_url(item.get("play_url")), "audio", "收藏音乐"
                    ),
                }
            )
    return catalog.commit(
        {
            "access_mode": "login_cookie",
            "items": items,
            "pagination": _pagination(result, cursor, len(items)),
        },
        registry,
    )


async def fetch_feed(
    kind: Literal["recommended", "following", "friends"],
    cursor: int,
    count: int,
    cookie_store: LoginCookieStore,
    registry: MediaRegistry,
) -> dict[str, Any]:
    cookie = (
        cookie_store.get() if kind == "recommended" else _require_login(cookie_store)
    )
    if kind == "recommended":
        method, params = "fetch_post_feed", PostFeed(count=count)
    elif kind == "following":
        method, params = "fetch_follow_feed", FollowFeed(cursor=cursor, count=count)
    else:
        method, params = "fetch_friend_feed", FriendFeed(cursor=cursor)
    result = await _request(cookie, method, params)
    return _post_payload(result, cookie, cursor, registry)


async def search_user_posts(
    sec_user_id: str,
    keyword: str,
    cursor: int,
    count: int,
    cookie_store: LoginCookieStore,
    registry: MediaRegistry,
) -> dict[str, Any]:
    cookie = cookie_store.get()
    result = await _request(
        cookie,
        "fetch_home_post_search",
        HomePostSearch(
            from_user=validate_sec_user_id(sec_user_id),
            keyword=keyword,
            offset=cursor,
            count=count,
        ),
    )
    payload = _post_payload(result, cookie, cursor, registry)
    payload["search_id"] = (result.get("log_pb") or {}).get("impr_id")
    return payload


async def fetch_suggestions(
    query: str, count: int, cookie_store: LoginCookieStore
) -> dict[str, Any]:
    cookie = cookie_store.get()
    result = await _request(
        cookie, "fetch_suggest_word", SuggestWord(query=query, count=count)
    )
    words: list[str] = []
    for group in result.get("data") or []:
        for item in (group.get("words") or []) if isinstance(group, dict) else []:
            word = item.get("word") if isinstance(item, dict) else item
            if word:
                words.append(str(word))
    return {"access_mode": _access_mode(cookie), "items": list(dict.fromkeys(words))}


def _live_payload(raw: dict[str, Any], catalog: MediaCatalog) -> dict[str, Any]:
    wrapper = raw
    room = raw.get("room") if isinstance(raw.get("room"), dict) else raw
    owner = room.get("owner") or room.get("user") or {}
    stream = room.get("stream_url") or {}
    stats = room.get("stats") or {}
    view_stats = room.get("room_view_stats") or {}
    return {
        "room_id": str(
            room.get("id_str") or room.get("id") or room.get("room_id") or ""
        ),
        "web_rid": str(wrapper.get("web_rid") or room.get("web_rid") or ""),
        "title": room.get("title") or "",
        "status": room.get("status"),
        "viewer_count": room.get("user_count")
        or stats.get("user_count_str")
        or view_stats.get("display_value"),
        "owner": _user_summary(owner, catalog),
        "cover": catalog.prepare(
            first_url(room.get("cover") or room.get("background")), "image", "直播封面"
        ),
        "flv_url": stream.get("flv_pull_url") or stream.get("flv_pull_url_params"),
        "hls_url": stream.get("hls_pull_url") or stream.get("hls_pull_url_params"),
    }


async def fetch_live_room(
    room_id: str, cookie_store: LoginCookieStore, registry: MediaRegistry
) -> dict[str, Any]:
    cookie = cookie_store.get()
    result = await _request(cookie, "fetch_live_room_id", UserLive2(room_id=room_id))
    raw = result.get("data") or result
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    catalog = MediaCatalog(build_douyin_headers(cookie))
    return catalog.commit(
        {"access_mode": _access_mode(cookie), "live": _live_payload(raw, catalog)},
        registry,
    )


async def fetch_live_status(
    user_id: str, cookie_store: LoginCookieStore
) -> dict[str, Any]:
    cookie = cookie_store.get()
    result = await _request(
        cookie, "fetch_user_live_status", UserLiveStatus(user_ids=user_id)
    )
    return {"access_mode": _access_mode(cookie), "items": result.get("data") or []}


async def fetch_live_messages(
    room_id: str,
    user_unique_id: str,
    cookie_store: LoginCookieStore,
) -> dict[str, Any]:
    cookie = cookie_store.get()
    result = await _request(
        cookie,
        "fetch_live_im_fetch",
        LiveImFetch(room_id=room_id, user_unique_id=user_unique_id),
    )
    return {
        "access_mode": _access_mode(cookie),
        "items": result.get("data") or [],
        "cursor": (result.get("extra") or {}).get("cursor"),
        "internal_ext": result.get("internal_ext"),
        "raw": result,
    }


async def fetch_account_profile(
    cookie_store: LoginCookieStore, registry: MediaRegistry
) -> dict[str, Any]:
    cookie = _require_login(cookie_store)
    result = await _request(cookie, "fetch_query_user", QueryUser())
    raw = result.get("user") or result.get("data") or result
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    if isinstance(raw, dict) and isinstance(raw.get("user"), dict):
        raw = raw["user"]
    catalog = MediaCatalog(build_douyin_headers(cookie))
    profile = _user_summary(raw, catalog)
    if not profile.get("uid") and result.get("user_uid"):
        profile["uid"] = str(result["user_uid"])
    if profile.get("nickname") == "未知用户":
        profile["nickname"] = "当前登录标识"
    return catalog.commit(
        {"access_mode": "login_cookie", "profile": profile, "raw": result}, registry
    )


async def fetch_following_live(
    cookie_store: LoginCookieStore, registry: MediaRegistry
) -> dict[str, Any]:
    cookie = _require_login(cookie_store)
    result = await _request(cookie, "fetch_following_live", FollowingUserLive())
    raw_items = result.get("data") or result.get("rooms") or []
    if isinstance(raw_items, dict):
        raw_items = raw_items.get("data") or raw_items.get("rooms") or []
    catalog = MediaCatalog(build_douyin_headers(cookie))
    items = [
        _live_payload(item, catalog) for item in raw_items if isinstance(item, dict)
    ]
    return catalog.commit({"access_mode": "login_cookie", "items": items}, registry)
