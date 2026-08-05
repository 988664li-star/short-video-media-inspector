import pytest

from backend.app.services.douyin import capabilities, resolver, users
from backend.app.services.douyin.client import (
    anonymous_douyin_cookie,
    build_douyin_headers,
)
from backend.app.services.douyin.helpers import (
    audio_urls,
    image_entries,
    url_list,
    validate_sec_user_id,
    video_urls,
)
from backend.app.services.media import MediaRegistry
from backend.app.services.session import LoginCookieStore, normalize_login_cookie


def test_normalize_login_cookie_accepts_request_header_value():
    cookie, names = normalize_login_cookie(
        "Cookie: sessionid=secret==; ttwid=device; msToken=token;"
    )
    assert cookie == "sessionid=secret==; ttwid=device; msToken=token;"
    assert names == ["sessionid", "ttwid", "msToken"]


def test_login_cookie_store_restores_after_restart_and_uses_private_file(tmp_path):
    storage_path = tmp_path / "private" / "douyin_cookie.json"
    first_store = LoginCookieStore(storage_path)
    status = first_store.set("sessionid=private-value; ttwid=device-value;")

    assert status["storage"] == "backend_file"
    assert storage_path.exists()
    assert storage_path.stat().st_mode & 0o777 == 0o600
    assert storage_path.parent.stat().st_mode & 0o777 == 0o700

    restored_store = LoginCookieStore(storage_path)
    assert restored_store.status()["configured"] is True
    assert restored_store.get() == ("sessionid=private-value; ttwid=device-value;")

    restored_store.clear()
    assert not storage_path.exists()


def test_anonymous_cookie_is_reused_for_cursor_pagination(monkeypatch):
    anonymous_douyin_cookie.cache_clear()
    monkeypatch.setattr(
        "backend.app.services.douyin.client.TokenManager.gen_ttwid",
        lambda: "stable-device",
    )
    assert build_douyin_headers()["Cookie"] == "ttwid=stable-device;"
    assert build_douyin_headers()["Cookie"] == "ttwid=stable-device;"
    anonymous_douyin_cookie.cache_clear()


@pytest.mark.parametrize(
    "value",
    ["short", "MS4wLjAB 用户", "MS4wLjAB/user", "MS4wLjAB用户标识"],
)
def test_validate_sec_user_id_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="用户标识格式不正确"):
        validate_sec_user_id(value)


def test_url_helpers_cover_douyin_shapes():
    detail = {
        "video": {
            "bit_rate_audio": [
                {
                    "audio_meta": {
                        "url_list": {"main_url": "https://cdn.example/audio.m4a"}
                    }
                }
            ],
            "play_addr_h264": {"url_list": ["https://cdn.example/video.mp4"]},
            "cover": {"url_list": ["https://cdn.example/cover.jpg"]},
            "origin_cover": {"url_list": ["https://cdn.example/cover.jpg"]},
        },
        "images": [{"url_list": ["https://cdn.example/photo.jpg"]}],
    }
    assert audio_urls(detail) == ["https://cdn.example/audio.m4a"]
    assert video_urls(detail) == ["https://cdn.example/video.mp4"]
    assert image_entries(detail) == [
        {"label": "封面", "source_url": "https://cdn.example/cover.jpg"},
        {"label": "图集 1", "source_url": "https://cdn.example/photo.jpg"},
    ]
    assert url_list("file:///etc/passwd") == []


@pytest.mark.asyncio
async def test_user_posts_page_returns_cursor_and_proxied_covers(monkeypatch):
    async def fake_request(sec_user_id, max_cursor, count, headers):
        assert sec_user_id == "MS4wLjABAAAA-user-0123456789"
        assert max_cursor == 1_700_000_000
        assert count == 12
        assert "sessionid=test" in headers["Cookie"]
        return {
            "status_code": 0,
            "has_more": True,
            "max_cursor": 1_699_999_000,
            "aweme_list": [
                {
                    "aweme_id": "1234567890123456789",
                    "desc": "下一页作品",
                    "create_time": 1_700_000_000,
                    "author": {"nickname": "测试用户"},
                    "statistics": {"digg_count": 2, "comment_count": 1},
                    "video": {"cover": {"url_list": ["https://cdn.example/next.jpg"]}},
                }
            ],
        }

    monkeypatch.setattr(users, "_request_user_posts", fake_request)
    cookie_store = LoginCookieStore()
    cookie_store.set("sessionid=test; ttwid=device;")
    result = await users.fetch_user_posts_page(
        "MS4wLjABAAAA-user-0123456789",
        1_700_000_000,
        12,
        cookie_store,
        MediaRegistry(),
    )

    assert result["access_mode"] == "login_cookie"
    assert result["pagination"] == {
        "has_more": True,
        "next_cursor": 1_699_999_000,
    }
    assert result["posts"][0]["aweme_id"] == "1234567890123456789"
    assert result["posts"][0]["cover"]["proxy_url"].startswith("/api/media/")


def test_user_posts_pagination_stops_when_cursor_does_not_advance():
    assert users._pagination(
        {"has_more": True, "max_cursor": 1_700_000_000},
        current_cursor=1_700_000_000,
    ) == {"has_more": False, "next_cursor": 1_700_000_000}


def test_capability_post_payload_unwraps_feed_items_and_proxies_media():
    result = capabilities._post_payload(
        {
            "has_more": True,
            "cursor": 8,
            "data": [
                {
                    "aweme": {
                        "aweme_id": "1234567890123456789",
                        "desc": "Feed 作品",
                        "author": {"nickname": "作者"},
                        "statistics": {"digg_count": 3},
                        "video": {
                            "cover": {"url_list": ["https://cdn.example/feed.jpg"]}
                        },
                    }
                }
            ],
        },
        "",
        0,
        MediaRegistry(),
    )

    assert result["items"][0]["aweme_id"] == "1234567890123456789"
    assert result["items"][0]["cover"]["proxy_url"].startswith("/api/media/")
    assert result["pagination"] == {"has_more": True, "next_cursor": 8}


@pytest.mark.asyncio
async def test_related_posts_never_exposes_fake_pagination(monkeypatch):
    async def fake_request(*_args):
        return {
            "status_code": 0,
            "has_more": True,
            "aweme_list": [
                {
                    "aweme_id": "1234567890123456789",
                    "desc": "相关推荐",
                    "author": {"nickname": "作者"},
                }
            ],
        }

    monkeypatch.setattr(capabilities, "_request", fake_request)
    result = await capabilities.fetch_related_posts(
        "1234567890123456789",
        20,
        LoginCookieStore(),
        MediaRegistry(),
    )

    assert result["pagination"] == {"has_more": False, "next_cursor": None}


@pytest.mark.asyncio
async def test_login_capability_stops_before_upstream_request(monkeypatch):
    async def fail_request(*_args):
        raise AssertionError("游客模式不应请求登录接口")

    monkeypatch.setattr(capabilities, "_request", fail_request)
    with pytest.raises(capabilities.LoginRequiredError, match="sessionid"):
        await capabilities.fetch_connections(
            "following",
            "MS4wLjABAAAA-user-0123456789",
            "123",
            0,
            20,
            LoginCookieStore(),
            MediaRegistry(),
        )


@pytest.mark.asyncio
async def test_resolver_preserves_avatar_user_ids_and_media_proxy(monkeypatch):
    detail = {
        "aweme_id": "1234567890123456789",
        "desc": "测试作品",
        "create_time": 1_700_000_000,
        "duration": 15_000,
        "author": {
            "nickname": "测试作者",
            "sec_uid": "MS4wLjABAAAA-author-0123456789",
            "avatar_thumb": {"url_list": ["https://cdn.example/avatar.jpg"]},
        },
        "statistics": {"digg_count": 8, "comment_count": 1},
        "video": {
            "width": 1080,
            "height": 1920,
            "play_addr_h264": {"url_list": ["https://cdn.example/video.mp4"]},
            "bit_rate_audio": [
                {
                    "audio_meta": {
                        "url_list": {"main_url": "https://cdn.example/audio.m4a"}
                    }
                }
            ],
            "cover": {"url_list": ["https://cdn.example/cover.jpg"]},
        },
    }
    supplemental = {
        "comments": {
            "total": 1,
            "comments": [
                {
                    "cid": "comment-1",
                    "text": "很好",
                    "user": {
                        "nickname": "读者",
                        "sec_uid": "MS4wLjABAAAA-reader-0123456789",
                    },
                    "reply_comment": [
                        {
                            "cid": "reply-1",
                            "text": "谢谢",
                            "user": {
                                "nickname": "回复用户",
                                "sec_uid": "MS4wLjABAAAA-replier-0123456789",
                            },
                        }
                    ],
                }
            ],
        }
    }

    async def fake_fetch_aweme_detail(_aweme_id, _login_cookie):
        return detail, {"User-Agent": "test", "Cookie": "ttwid=test;"}

    async def fake_fetch_supplemental_data(*_args):
        return supplemental, {}

    monkeypatch.setattr(resolver, "fetch_aweme_detail", fake_fetch_aweme_detail)
    monkeypatch.setattr(
        resolver, "fetch_supplemental_data", fake_fetch_supplemental_data
    )
    cookie_store = LoginCookieStore()
    media_registry = MediaRegistry()

    result = await resolver.resolve_share_text(
        "https://www.douyin.com/video/1234567890123456789",
        cookie_store,
        media_registry,
        direct_aweme_id="1234567890123456789",
    )

    assert result["access_mode"] == "visitor"
    assert result["audio"]["proxy_url"].startswith("/api/media/")
    assert result["comments"]["items"][0]["user"]["sec_user_id"].endswith(
        "reader-0123456789"
    )
    assert result["comments"]["items"][0]["replies"][0]["user"]["sec_user_id"].endswith(
        "replier-0123456789"
    )
