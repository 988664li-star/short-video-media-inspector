from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any
from urllib.parse import quote

from f2.apps.douyin.crawler import DouyinCrawler
from f2.apps.douyin.model import (
    PostComment,
    PostDetail,
    PostRelated,
    UserPost,
    UserProfile,
)
from f2.apps.douyin.utils import ClientConfManager, TokenManager


@lru_cache(maxsize=1)
def anonymous_douyin_cookie() -> str:
    """Keep one visitor identity for cursor pagination during this process."""
    return f"ttwid={TokenManager.gen_ttwid()};"


def build_douyin_headers(login_cookie: str = "") -> dict[str, str]:
    request_cookie = login_cookie or anonymous_douyin_cookie()
    return {
        "User-Agent": ClientConfManager.user_agent(),
        "Referer": ClientConfManager.referer(),
        "Cookie": request_cookie,
    }


def crawler_kwargs(headers: dict[str, str], *, max_retries: int = 2) -> dict[str, Any]:
    return {
        "headers": headers,
        "cookie": headers.get("Cookie", ""),
        "proxies": ClientConfManager.proxies(),
        "timeout": 20,
        "max_retries": max_retries,
    }


async def fetch_aweme_detail(
    aweme_id: str,
    login_cookie: str = "",
) -> tuple[dict[str, Any], dict[str, str]]:
    headers = build_douyin_headers(login_cookie)
    async with DouyinCrawler(crawler_kwargs(headers, max_retries=3)) as crawler:
        response = await crawler.fetch_post_detail(PostDetail(aweme_id=aweme_id))
    detail = response.get("aweme_detail")
    if not detail:
        raise RuntimeError("没有获取到作品详情，作品可能已删除、设为私密或触发风控")
    return detail, headers


async def fetch_supplemental_data(
    aweme_id: str,
    sec_user_id: str | None,
    headers: dict[str, str],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Fetch optional public data without making the core parse fail."""
    kwargs = crawler_kwargs(headers)

    async def request(method_name: str, params: Any) -> dict[str, Any]:
        async with DouyinCrawler(kwargs) as crawler:
            return await getattr(crawler, method_name)(params)

    requests = {
        "comments": request(
            "fetch_post_comment", PostComment(aweme_id=aweme_id, count=20)
        ),
        "related": request(
            "fetch_post_related",
            PostRelated(
                aweme_id=aweme_id,
                count=10,
                filterGids=quote(f"{aweme_id},"),
            ),
        ),
    }
    if sec_user_id:
        requests["profile"] = request(
            "fetch_user_profile", UserProfile(sec_user_id=sec_user_id)
        )
        requests["author_posts"] = request(
            "fetch_user_post",
            UserPost(max_cursor=0, count=9, sec_user_id=sec_user_id),
        )

    names = list(requests)
    results = await asyncio.gather(*requests.values(), return_exceptions=True)
    data: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            errors[name] = str(result)
        elif isinstance(result, dict) and result.get("status_code") in (None, 0):
            data[name] = result
        elif isinstance(result, dict):
            errors[name] = str(result.get("status_msg") or "接口未返回公开数据")
    return data, errors
