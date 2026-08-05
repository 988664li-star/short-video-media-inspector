from __future__ import annotations

from typing import Any

from f2.apps.douyin.utils import AwemeIdFetcher
from f2.utils.utils import extract_valid_urls

from backend.app.services.douyin.catalog import MediaCatalog
from backend.app.services.douyin.client import (
    fetch_aweme_detail,
    fetch_supplemental_data,
)
from backend.app.services.douyin.helpers import (
    audio_urls,
    first_url,
    format_time,
    image_entries,
    video_urls,
)
from backend.app.services.media import MediaRegistry
from backend.app.services.session import LoginCookieStore


def normalize_aweme_id(value: str | None) -> str | None:
    if not value:
        return None
    aweme_id = str(value).strip()
    if not aweme_id.isdigit() or not 10 <= len(aweme_id) <= 30:
        raise ValueError("作品 ID 格式不正确")
    return aweme_id


def summarize_user(user: dict[str, Any], catalog: MediaCatalog) -> dict[str, Any]:
    return {
        "nickname": user.get("nickname") or "未知用户",
        "unique_id": user.get("unique_id") or "",
        "sec_user_id": user.get("sec_uid") or "",
        "avatar": catalog.prepare(
            first_url(user.get("avatar_thumb") or user.get("avatar_medium")),
            "image",
            "头像",
        ),
    }


def summarize_comments(
    comments_raw: dict[str, Any],
    catalog: MediaCatalog,
) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for comment in comments_raw.get("comments") or []:
        comment_images = [
            media
            for index, image in enumerate(comment.get("image_list") or [], start=1)
            if (
                media := catalog.prepare(first_url(image), "image", f"评论图片 {index}")
            )
        ]
        replies = []
        for reply in comment.get("reply_comment") or []:
            replies.append(
                {
                    "id": str(reply.get("cid") or ""),
                    "text": reply.get("text") or "",
                    "created_at": format_time(reply.get("create_time")),
                    "likes": reply.get("digg_count"),
                    "ip_label": reply.get("ip_label"),
                    "user": summarize_user(reply.get("user") or {}, catalog),
                }
            )
        comments.append(
            {
                "id": str(comment.get("cid") or ""),
                "text": comment.get("text") or "",
                "created_at": format_time(comment.get("create_time")),
                "likes": comment.get("digg_count"),
                "reply_total": comment.get("reply_comment_total"),
                "is_hot": comment.get("is_hot"),
                "is_author_liked": comment.get("is_author_digged"),
                "ip_label": comment.get("ip_label"),
                "label": comment.get("label_text"),
                "user": summarize_user(comment.get("user") or {}, catalog),
                "images": comment_images,
                "replies": replies,
            }
        )
    return comments


def summarize_aweme(item: dict[str, Any], catalog: MediaCatalog) -> dict[str, Any]:
    video = item.get("video") or {}
    author = item.get("author") or {}
    aweme_id = str(item.get("aweme_id") or "")
    return {
        "aweme_id": aweme_id,
        "description": item.get("desc") or "（无作品描述）",
        "created_at": format_time(item.get("create_time")),
        "duration_ms": item.get("duration") or video.get("duration"),
        "aweme_type": item.get("aweme_type"),
        "author": {
            "nickname": author.get("nickname") or "未知作者",
            "unique_id": author.get("unique_id") or "",
        },
        "statistics": {
            "likes": (item.get("statistics") or {}).get("digg_count"),
            "comments": (item.get("statistics") or {}).get("comment_count"),
        },
        "cover": catalog.prepare(
            first_url(video.get("cover") or video.get("origin_cover")),
            "image",
            "作品封面",
        ),
        "douyin_url": (
            f"https://www.douyin.com/video/{aweme_id}" if aweme_id else None
        ),
    }


def build_author_profile(
    profile_user: dict[str, Any],
    author: dict[str, Any],
    avatar: dict[str, str] | None,
) -> dict[str, Any]:
    profile = profile_user or author
    return {
        "nickname": profile.get("nickname") or author.get("nickname") or "未知作者",
        "signature": profile.get("signature") or author.get("signature"),
        "unique_id": profile.get("unique_id") or author.get("unique_id"),
        "short_id": profile.get("short_id") or author.get("short_id"),
        "uid": profile.get("uid") or author.get("uid"),
        "sec_user_id": profile.get("sec_uid") or author.get("sec_uid"),
        "follower_count": profile.get("follower_count"),
        "following_count": profile.get("following_count"),
        "total_favorited": profile.get("total_favorited"),
        "aweme_count": profile.get("aweme_count"),
        "favoriting_count": profile.get("favoriting_count"),
        "mix_count": profile.get("mix_count"),
        "city": profile.get("city"),
        "country": profile.get("country"),
        "ip_location": profile.get("ip_location"),
        "gender": profile.get("gender"),
        "user_age": profile.get("user_age"),
        "live_status": profile.get("live_status"),
        "is_ban": profile.get("is_ban"),
        "avatar_url": avatar.get("proxy_url") if avatar else None,
    }


async def resolve_share_text(
    share_text: str,
    cookie_store: LoginCookieStore,
    media_registry: MediaRegistry,
    direct_aweme_id: str | None = None,
) -> dict[str, Any]:
    """Resolve one share URL and normalize all data consumed by the frontend."""
    valid_url = extract_valid_urls(share_text)
    if not isinstance(valid_url, str):
        raise ValueError("分享内容中没有找到有效的 HTTP/HTTPS 链接")
    aweme_id = normalize_aweme_id(direct_aweme_id)
    if aweme_id is None:
        aweme_id = await AwemeIdFetcher.get_aweme_id(valid_url)

    active_cookie = cookie_store.get()
    detail, headers = await fetch_aweme_detail(aweme_id, active_cookie)
    author = detail.get("author") or {}
    video = detail.get("video") or {}
    music = detail.get("music") or {}
    supplemental, supplemental_errors = await fetch_supplemental_data(
        str(aweme_id), author.get("sec_uid"), headers
    )
    catalog = MediaCatalog(headers)

    audio_sources = audio_urls(detail)
    video_sources = video_urls(detail)
    audio = catalog.prepare(
        audio_sources[0] if audio_sources else None, "audio", "视频原音"
    )
    playable_video = catalog.prepare(
        video_sources[0] if video_sources else None, "video", "无水印视频"
    )
    images = [
        catalog.prepare(item["source_url"], "image", item["label"])
        for item in image_entries(detail)
    ]
    profile_user = (supplemental.get("profile") or {}).get("user") or {}
    avatar = catalog.prepare(
        first_url(profile_user.get("avatar_larger") or author.get("avatar_thumb")),
        "image",
        "作者头像",
    )
    music_audio = catalog.prepare(first_url(music.get("play_url")), "audio", "作品配乐")
    music_cover = catalog.prepare(
        first_url(music.get("cover_large") or music.get("cover_medium")),
        "image",
        "原声封面",
    )
    comments_raw = supplemental.get("comments") or {}
    comments = summarize_comments(comments_raw, catalog)
    related_items = [
        summarize_aweme(item, catalog)
        for item in (supplemental.get("related") or {}).get("aweme_list") or []
    ]
    author_posts = [
        summarize_aweme(item, catalog)
        for item in (supplemental.get("author_posts") or {}).get("aweme_list") or []
    ]

    statistics = detail.get("statistics") or {}
    status = detail.get("status") or {}
    aweme_control = detail.get("aweme_control") or {}
    video_control = detail.get("video_control") or {}
    mix = detail.get("mix_info") or {}
    bit_rates = [
        {
            "gear": item.get("gear_name"),
            "bit_rate": item.get("bit_rate"),
            "format": item.get("format"),
            "fps": item.get("FPS"),
            "codec": "H.265" if item.get("is_h265") else "H.264",
            "quality_type": item.get("quality_type"),
            "data_size": (item.get("play_addr") or {}).get("data_size"),
        }
        for item in video.get("bit_rate") or []
    ]
    payload = {
        "access_mode": "login_cookie" if active_cookie else "visitor",
        "aweme_id": str(detail.get("aweme_id") or aweme_id),
        "share_url": valid_url,
        "description": detail.get("desc") or "（无作品描述）",
        "caption": detail.get("caption"),
        "created_at": format_time(detail.get("create_time")),
        "duration_ms": detail.get("duration") or video.get("duration") or 0,
        "width": video.get("width"),
        "height": video.get("height"),
        "author": build_author_profile(profile_user, author, avatar),
        "statistics": {
            "admires": statistics.get("admire_count"),
            "likes": statistics.get("digg_count"),
            "comments": statistics.get("comment_count"),
            "shares": statistics.get("share_count"),
            "collects": statistics.get("collect_count"),
            "plays": statistics.get("play_count"),
        },
        "hashtags": [
            {
                "id": str(item.get("hashtag_id") or ""),
                "name": item.get("hashtag_name") or "",
            }
            for item in detail.get("text_extra") or []
            if item.get("hashtag_name")
        ],
        "content": {
            "aweme_type": detail.get("aweme_type"),
            "media_type": detail.get("media_type"),
            "region": detail.get("region"),
            "position": detail.get("position"),
            "is_ads": detail.get("is_ads"),
            "is_story": detail.get("is_story"),
            "is_top": detail.get("is_top"),
            "comment_gid": detail.get("comment_gid"),
        },
        "permissions": {
            "can_comment": aweme_control.get("can_comment"),
            "can_forward": aweme_control.get("can_forward"),
            "can_share": aweme_control.get("can_share"),
            "can_show_comment": aweme_control.get("can_show_comment"),
            "allow_share": video_control.get("allow_share"),
            "allow_douplus": video_control.get("allow_douplus"),
            "download_setting": video_control.get("download_setting"),
        },
        "status": {
            "private_status": status.get("private_status"),
            "is_delete": status.get("is_delete"),
            "is_prohibited": status.get("is_prohibited"),
            "part_see": status.get("part_see"),
        },
        "music": {
            "id": str(music.get("id") or ""),
            "mid": music.get("mid"),
            "title": music.get("title"),
            "author": music.get("author"),
            "duration_seconds": music.get("duration"),
            "status": music.get("status"),
            "is_original": music.get("is_original"),
            "is_original_sound": music.get("is_original_sound"),
            "is_commerce_music": music.get("is_commerce_music"),
            "is_pgc": music.get("is_pgc"),
            "owner_nickname": music.get("owner_nickname"),
            "owner_id": music.get("owner_id"),
            "audio": music_audio,
            "cover": music_cover,
        },
        "mix": {
            "id": str(mix.get("mix_id") or ""),
            "name": mix.get("mix_name"),
            "description": mix.get("mix_desc"),
            "type": mix.get("mix_type"),
            "share_url": mix.get("mix_share_url"),
            "created_at": format_time(mix.get("mix_create_time")),
            "updated_at": format_time(mix.get("mix_update_time")),
        },
        "ocr_text": (detail.get("seo_info") or {}).get("seo_ocr_content"),
        "video_technical": {
            "format": video.get("format"),
            "ratio": video.get("ratio"),
            "has_watermark": video.get("has_watermark"),
            "is_h265": video.get("is_h265"),
            "is_hdr": video.get("is_source_HDR"),
            "is_long_video": video.get("is_long_video"),
            "bit_rates": bit_rates,
        },
        "audio": audio,
        "video": playable_video,
        "images": images,
        "comments": {
            "total": comments_raw.get("total"),
            "has_more": comments_raw.get("has_more"),
            "items": comments,
        },
        "related": related_items,
        "author_posts": author_posts,
        "supplemental_errors": supplemental_errors,
        "warnings": (
            []
            if audio_sources
            else ["这条作品没有返回独立音轨地址，页面仍会展示可用的视频和图片。"]
        ),
        "raw_detail": detail,
    }
    return catalog.commit(payload, media_registry)
