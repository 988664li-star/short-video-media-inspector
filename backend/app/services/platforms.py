from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from f2.utils.utils import extract_valid_urls


Platform = Literal["douyin", "tiktok"]
RequestedPlatform = Literal["auto", "douyin", "tiktok"]


def share_url_from_text(share_text: str) -> str:
    url = extract_valid_urls(share_text)
    if not isinstance(url, str):
        raise ValueError("分享内容中没有找到有效的 HTTP/HTTPS 链接")
    return url.rstrip("。.,，!！?？）)]}〉》\"")


def detect_platform(share_url: str) -> Platform:
    host = (urlparse(share_url).hostname or "").lower()
    if host == "tiktok.com" or host.endswith(".tiktok.com"):
        return "tiktok"
    if host == "douyin.com" or host.endswith(".douyin.com") or host.endswith(".iesdouyin.com"):
        return "douyin"
    raise ValueError("暂只支持抖音或 TikTok 作品链接")


def resolve_platform(share_url: str, requested: RequestedPlatform) -> Platform:
    detected = detect_platform(share_url)
    if requested != "auto" and requested != detected:
        name = "TikTok" if detected == "tiktok" else "抖音"
        raise ValueError(f"当前链接属于{name}，请切换为自动识别或选择正确的平台")
    return detected
