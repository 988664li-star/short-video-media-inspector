import httpx
import pytest

from backend.app.services.canvas_projects.extraction import (
    CanvasMediaExtractionService,
    _ResolvedOutput,
)
from backend.app.services.canvas_projects import CanvasProjectService
from backend.app.services.media import MediaRegistry, MediaResource
from backend.app.services.session import LoginCookieStore


@pytest.mark.asyncio
async def test_materialize_extracts_video_audio_separately_from_platform_music(tmp_path):
    project_service = CanvasProjectService(
        tmp_path / "canvas.sqlite3",
        tmp_path / "canvas",
    )
    project_service.initialize()
    project = project_service.create_project("提取测试")
    registry = MediaRegistry()
    session_id = registry.add([
        MediaResource("https://media.test/video", {}, "video"),
        MediaResource("https://media.test/audio", {}, "audio"),
    ])

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/video":
            return httpx.Response(200, content=b"video", headers={"Content-Type": "video/mp4"})
        return httpx.Response(200, content=b"audio", headers={"Content-Type": "audio/mpeg"})

    service = CanvasMediaExtractionService(
        project_service,
        LoginCookieStore(),
        registry,
        1024,
        transport=httpx.MockTransport(respond),
    )
    service._remove_video_audio = lambda content, mime_type: (content, mime_type)
    service._extract_video_audio = lambda content, mime_type: (b"mixed-video-audio", "audio/mp4")
    outputs, warnings = await service._materialize(
        project["id"],
        "1234567890",
        [
            _ResolvedOutput("video", "原视频", {"proxy_url": f"/api/media/{session_id}/0"}),
            _ResolvedOutput("music", "作品配乐", {"proxy_url": f"/api/media/{session_id}/1"}),
            _ResolvedOutput("audio", "视频混合音频", {"proxy_url": f"/api/media/{session_id}/1"}),
        ],
    )

    assert outputs["video"]["available"] is True
    assert outputs["music"]["asset"]["id"] != outputs["audio"]["asset"]["id"]
    assert outputs["audio"]["asset"]["filename"].endswith("-video-audio.m4a")
    assert outputs["audio"]["message"] == "已直接从原视频文件提取完整音轨，包含人声、配乐和音效"
    assert len(project_service.list_assets(project["id"])) == 3
    assert warnings == []


@pytest.mark.asyncio
async def test_materialize_keeps_unavailable_output_explicit(tmp_path):
    project_service = CanvasProjectService(
        tmp_path / "canvas.sqlite3",
        tmp_path / "canvas",
    )
    project_service.initialize()
    project = project_service.create_project("缺失音轨")
    service = CanvasMediaExtractionService(
        project_service,
        LoginCookieStore(),
        MediaRegistry(),
        1024,
    )

    outputs, warnings = await service._materialize(
        project["id"],
        "1234567890",
        [
            _ResolvedOutput("video", "原视频", None),
            _ResolvedOutput("music", "作品配乐", None),
            _ResolvedOutput("audio", "视频混合音频", None),
        ],
    )

    assert warnings == []
    assert outputs["video"]["available"] is False
    assert outputs["music"]["asset"] is None
    assert outputs["audio"]["message"] == "原视频文件不包含可提取的音轨"
