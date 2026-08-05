from __future__ import annotations

from datetime import datetime
from typing import Any


def dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def url_list(value: Any) -> list[str]:
    """Read the URL container shapes used throughout Douyin responses."""
    if isinstance(value, str):
        return [value] if value.startswith(("http://", "https://")) else []
    if isinstance(value, list):
        urls: list[str] = []
        for item in value:
            urls.extend(url_list(item))
        return dedupe(urls)
    if not isinstance(value, dict):
        return []

    container = value.get("url_list")
    if container is None and any(
        key in value for key in ("main_url", "backup_url", "fallback_url")
    ):
        container = value
    if isinstance(container, dict):
        return dedupe(
            [
                container.get("main_url", ""),
                container.get("backup_url", ""),
                container.get("fallback_url", ""),
            ]
        )
    if container is not None:
        return url_list(container)
    return []


def first_url(value: Any) -> str | None:
    urls = url_list(value)
    return urls[0] if urls else None


def audio_urls(detail: dict[str, Any]) -> list[str]:
    streams = (detail.get("video") or {}).get("bit_rate_audio") or []
    urls: list[str] = []
    for stream in streams:
        if isinstance(stream, dict):
            urls.extend(url_list((stream.get("audio_meta") or {}).get("url_list")))
    return dedupe(urls)


def video_urls(detail: dict[str, Any]) -> list[str]:
    video = detail.get("video") or {}
    urls: list[str] = []
    for key in ("play_addr_h264", "play_addr"):
        urls.extend(url_list(video.get(key)))
    for item in video.get("bit_rate") or []:
        if isinstance(item, dict) and not item.get("is_h265"):
            urls.extend(url_list(item.get("play_addr")))
    return dedupe(urls)


def image_entries(detail: dict[str, Any]) -> list[dict[str, str]]:
    video = detail.get("video") or {}
    images: list[dict[str, str]] = []
    for label, key in (
        ("封面", "cover"),
        ("原始封面", "origin_cover"),
        ("动态封面", "dynamic_cover"),
    ):
        if source := first_url(video.get(key)):
            images.append({"label": label, "source_url": source})
    for index, image in enumerate(detail.get("images") or [], start=1):
        if source := first_url(image):
            images.append({"label": f"图集 {index}", "source_url": source})

    seen: set[str] = set()
    return [
        item
        for item in images
        if item["source_url"] not in seen and not seen.add(item["source_url"])
    ]


def format_time(timestamp: Any) -> str:
    try:
        return (
            datetime.fromtimestamp(int(timestamp))
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S")
        )
    except (TypeError, ValueError, OSError):
        return "—"


def validate_sec_user_id(value: Any) -> str:
    sec_user_id = str(value or "").strip()
    if not 10 <= len(sec_user_id) <= 256:
        raise ValueError("用户标识格式不正确")
    try:
        sec_user_id.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("用户标识格式不正确") from exc
    if any(character.isspace() or character in "/\\" for character in sec_user_id):
        raise ValueError("用户标识格式不正确")
    return sec_user_id
