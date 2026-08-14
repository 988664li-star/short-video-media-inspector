from __future__ import annotations

import html
import json
import re
from typing import Any

import httpx

from backend.app.services.douyin.catalog import MediaCatalog
from backend.app.services.douyin.helpers import first_url, format_time
from backend.app.services.media import MediaRegistry


TIKTOK_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
HYDRATION_PATTERN = re.compile(
    r"<script[^>]+id=[\"']__UNIVERSAL_DATA_FOR_REHYDRATION__[\"'][^>]*>(.*?)</script>",
    re.DOTALL,
)


def _url(value: Any) -> str | None:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    return first_url(value)


def _image_entries(video: dict[str, Any]) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    for label, key in (("封面", "cover"), ("原始封面", "originCover"), ("动态封面", "dynamicCover")):
        if source := _url(video.get(key)):
            images.append({"label": label, "source_url": source})
    return images


async def _fetch_item(share_url: str) -> tuple[dict[str, Any], str, str]:
    headers = {
        "User-Agent": TIKTOK_USER_AGENT,
        "Referer": "https://www.tiktok.com/",
        "Accept-Language": "en-US,en;q=0.9",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=25) as client:
        response = await client.get(share_url)
    response.raise_for_status()
    match = HYDRATION_PATTERN.search(response.text)
    if not match:
        raise RuntimeError("TikTok 页面未返回公开作品数据，可能受地区限制或作品不可见")
    try:
        scope = json.loads(html.unescape(match.group(1))).get("__DEFAULT_SCOPE__") or {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("TikTok 页面数据格式异常") from exc
    detail = scope.get("webapp.video-detail") or {}
    item = (detail.get("itemInfo") or {}).get("itemStruct") or {}
    if not item.get("id"):
        message = detail.get("statusMsg") or "作品可能已删除、设为私密或当前地区不可见"
        raise RuntimeError(f"没有获取到 TikTok 作品详情：{message}")
    cookie = "; ".join(f"{name}={value}" for name, value in response.cookies.items())
    return item, str(response.url), cookie


async def resolve_share_url(share_url: str, media_registry: MediaRegistry) -> dict[str, Any]:
    """Read public TikTok hydration data and shape it for the shared inspector UI."""
    detail, resolved_url, page_cookie = await _fetch_item(share_url)
    video = detail.get("video") or {}
    author = detail.get("author") or {}
    music = detail.get("music") or {}
    stats = detail.get("stats") or {}
    headers = {"User-Agent": TIKTOK_USER_AGENT, "Referer": "https://www.tiktok.com/"}
    if page_cookie:
        headers["Cookie"] = page_cookie
    catalog = MediaCatalog(headers)

    video_url = _url(video.get("playAddr")) or _url(video.get("downloadAddr"))
    audio_url = _url(music.get("playUrl"))
    images = [
        prepared
        for item in _image_entries(video)
        if (prepared := catalog.prepare(item["source_url"], "image", item["label"]))
    ]
    avatar = catalog.prepare(_url(author.get("avatarLarger") or author.get("avatarMedium")), "image", "作者头像")
    music_audio = catalog.prepare(audio_url, "audio", "作品配乐")
    music_cover = catalog.prepare(_url(music.get("coverLarge") or music.get("coverMedium")), "image", "原声封面")

    payload = {
        "platform": "tiktok",
        "access_mode": "visitor",
        "aweme_id": str(detail["id"]),
        "share_url": resolved_url,
        "description": detail.get("desc") or "（无作品描述）",
        "created_at": format_time(detail.get("createTime")),
        "duration_ms": (video.get("duration") or 0) * 1000,
        "width": video.get("width"),
        "height": video.get("height"),
        "author": {
            "nickname": author.get("nickname") or "未知作者",
            "unique_id": author.get("uniqueId") or "",
            "uid": author.get("id"),
            "sec_user_id": author.get("secUid"),
            "signature": author.get("signature"),
            "avatar_url": avatar.get("proxy_url") if avatar else None,
        },
        "statistics": {
            "likes": stats.get("diggCount"),
            "comments": stats.get("commentCount"),
            "shares": stats.get("shareCount"),
            "collects": stats.get("collectCount"),
            "plays": stats.get("playCount"),
        },
        "hashtags": [
            {"id": str(item.get("hashtagId") or item.get("awemeId") or ""), "name": item.get("hashtagName") or item.get("hashtag_name") or ""}
            for item in detail.get("textExtra") or []
            if item.get("hashtagName") or item.get("hashtag_name")
        ],
        "content": {
            "aweme_type": detail.get("itemType"),
            "media_type": detail.get("imagePost") and "image" or "video",
            "region": detail.get("region"),
            "is_ads": detail.get("isAd"),
        },
        "permissions": {
            "can_comment": detail.get("itemCommentStatus"),
            "can_share": detail.get("shareEnabled"),
            "download_setting": author.get("downloadSetting"),
        },
        "status": {
            "private_status": detail.get("privateItem"),
            "is_delete": detail.get("isDelete"),
            "is_prohibited": detail.get("isContentClassified"),
        },
        "music": {
            "id": str(music.get("id") or ""),
            "title": music.get("title"),
            "author": music.get("authorName"),
            "duration_seconds": music.get("duration"),
            "is_original": music.get("original"),
            "audio": music_audio,
            "cover": music_cover,
        },
        "video_technical": {
            "format": video.get("format"),
            "ratio": video.get("ratio"),
            "has_watermark": video.get("hasWatermark"),
            "is_h265": video.get("codecType") == "h265",
            "bit_rates": [
                {
                    "gear": item.get("GearName") or item.get("gearName"),
                    "bit_rate": item.get("Bitrate") or item.get("bitrate"),
                    "codec": item.get("CodecType") or item.get("codecType"),
                    "data_size": item.get("DataSize") or item.get("dataSize"),
                }
                for item in video.get("bitrateInfo") or []
                if isinstance(item, dict)
            ],
        },
        "audio": catalog.prepare(audio_url, "audio", "视频原音"),
        "video": catalog.prepare(video_url, "video", "TikTok 视频"),
        "images": images,
        "comments": {"total": stats.get("commentCount"), "has_more": False, "items": []},
        "related": [],
        "author_posts": [],
        "warnings": [],
        "raw_detail": detail,
    }
    if not video_url:
        payload["warnings"].append("TikTok 页面没有返回可播放的视频地址，但其余公开信息仍可查看。")
    return catalog.commit(payload, media_registry)
