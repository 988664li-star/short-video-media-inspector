import httpx
import pytest

from backend.app.dependencies import (
    get_cookie_store,
    get_media_registry,
    get_shot_detection_service,
    get_transcription_service,
)
from backend.app.main import app
from backend.app.services.media import MediaRegistry, MediaResource
from backend.app.services.session import LoginCookieStore


@pytest.fixture(autouse=True)
def isolated_services(tmp_path):
    cookie_store = LoginCookieStore(tmp_path / "douyin_cookie.json")
    media_registry = MediaRegistry()
    app.dependency_overrides[get_cookie_store] = lambda: cookie_store
    app.dependency_overrides[get_media_registry] = lambda: media_registry
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as async_client:
        yield async_client


@pytest.mark.asyncio
async def test_health_and_initial_session_status(client: httpx.AsyncClient):
    assert (await client.get("/api/health")).json()["status"] == "ok"
    assert (await client.get("/api/session/status")).json() == {
        "configured": False,
        "cookie_count": 0,
        "has_login_markers": False,
        "storage": "backend_file",
        "storage_error": None,
    }


@pytest.mark.asyncio
async def test_cookie_lifecycle_never_returns_cookie_value(client: httpx.AsyncClient):
    response = await client.post(
        "/api/session/cookie",
        json={"cookie": "sessionid=private-value; ttwid=device-value;"},
    )
    assert response.status_code == 200
    assert response.json()["has_login_markers"] is True
    assert "private-value" not in response.text

    cleared = await client.delete("/api/session/cookie")
    assert cleared.status_code == 200
    assert cleared.json()["configured"] is False


@pytest.mark.asyncio
async def test_cookie_validation_is_reported_as_bad_request(client: httpx.AsyncClient):
    response = await client.post(
        "/api/session/cookie",
        json={"cookie": "Set-Cookie: sessionid=unsafe"},
    )
    assert response.status_code == 400
    assert "不要粘贴 Set-Cookie" in response.json()["detail"]


@pytest.mark.asyncio
async def test_request_schema_rejects_unknown_fields(client: httpx.AsyncClient):
    response = await client.post(
        "/api/resolve",
        json={"share_text": "https://v.douyin.com/example", "unknown": True},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_capability_reports_unauthorized_without_cookie(
    client: httpx.AsyncClient,
):
    response = await client.post(
        "/api/capabilities/account-library",
        json={"kind": "collections", "cursor": 0, "count": 12},
    )
    assert response.status_code == 401
    assert "登录 Cookie" in response.json()["detail"]


@pytest.mark.asyncio
async def test_capability_schema_requires_mix_id(client: httpx.AsyncClient):
    response = await client.post(
        "/api/capabilities/user-content",
        json={"kind": "mix", "cursor": 0, "count": 12},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_transcription_only_uses_registered_audio(client: httpx.AsyncClient):
    class StubTranscriptionService:
        async def transcribe(self, aweme_id, resource, context):
            assert aweme_id == "1234567890123456789"
            assert resource.kind == "audio"
            assert context == "剪辑教程"
            return {
                "aweme_id": aweme_id,
                "text": "测试文案",
                "segments": [],
                "language": "zh",
                "cached": False,
            }

    media_registry = app.dependency_overrides[get_media_registry]()
    session_id = media_registry.add(
        [
            MediaResource(
                source_url="https://cdn.example/audio.m4a",
                headers={"User-Agent": "test"},
                kind="audio",
            )
        ]
    )
    app.dependency_overrides[get_transcription_service] = (
        lambda: StubTranscriptionService()
    )

    response = await client.post(
        "/api/transcription",
        json={
            "aweme_id": "1234567890123456789",
            "media_url": f"/api/media/{session_id}/0",
            "context": "剪辑教程",
        },
    )

    assert response.status_code == 200
    assert response.json()["text"] == "测试文案"


@pytest.mark.asyncio
async def test_transcription_rejects_unregistered_media(client: httpx.AsyncClient):
    response = await client.post(
        "/api/transcription",
        json={
            "aweme_id": "1234567890123456789",
            "media_url": f"/api/media/{'0' * 32}/0",
        },
    )

    assert response.status_code == 410


@pytest.mark.asyncio
async def test_shot_detection_only_uses_registered_video(client: httpx.AsyncClient):
    class StubShotDetectionService:
        async def detect(self, aweme_id, resource):
            assert aweme_id == "1234567890123456789"
            assert resource.kind == "video"
            return {"aweme_id": aweme_id, "shots": [], "cached": False}

    media_registry = app.dependency_overrides[get_media_registry]()
    session_id = media_registry.add(
        [
            MediaResource(
                source_url="https://cdn.example/video.mp4",
                headers={"User-Agent": "test"},
                kind="video",
            )
        ]
    )
    app.dependency_overrides[get_shot_detection_service] = (
        lambda: StubShotDetectionService()
    )

    response = await client.post(
        "/api/shot-detection",
        json={
            "aweme_id": "1234567890123456789",
            "media_url": f"/api/media/{session_id}/0",
        },
    )

    assert response.status_code == 200
    assert response.json()["shots"] == []


@pytest.mark.asyncio
async def test_shot_detection_rejects_non_video_media(client: httpx.AsyncClient):
    media_registry = app.dependency_overrides[get_media_registry]()
    session_id = media_registry.add(
        [
            MediaResource(
                source_url="https://cdn.example/audio.m4a",
                headers={"User-Agent": "test"},
                kind="audio",
            )
        ]
    )

    response = await client.post(
        "/api/shot-detection",
        json={
            "aweme_id": "1234567890123456789",
            "media_url": f"/api/media/{session_id}/0",
        },
    )

    assert response.status_code == 400
    assert "不是视频" in response.json()["detail"]
