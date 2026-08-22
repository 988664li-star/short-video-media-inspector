import asyncio
import json

import httpx

from backend.app.services.video_generation import VideoGenerationRegistry
from backend.app.services.video_generation.contracts import (
    VideoEditRequest,
    VideoProviderContext,
)
from backend.app.services.video_generation.providers import (
    XiaoyunqueProviderConfig,
    XiaoyunqueVideoProvider,
)


def test_xiaoyunque_submit_uploads_video_and_images_then_creates_run():
    captured_submit: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "assets.example":
            if request.url.path.endswith(".mp4"):
                return httpx.Response(200, content=b"video", headers={"content-type": "video/mp4"})
            return httpx.Response(200, content=b"image", headers={"content-type": "image/png"})
        if request.url.path.endswith("/skill/upload_file"):
            body = request.content
            asset_id = "asset-video" if b"source.mp4" in body else "asset-image"
            return httpx.Response(200, json={"ret": "0", "data": {"pippit_asset_id": asset_id}})
        if request.url.path.endswith("/skill/submit_run"):
            captured_submit.update(json.loads(request.content))
            return httpx.Response(200, json={
                "ret": "0",
                "log_id": "log-submit",
                "data": {"run": {
                    "run_id": "run-1",
                    "thread_id": "thread-1",
                    "state": 1,
                }},
            })
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    provider = XiaoyunqueVideoProvider(
        XiaoyunqueProviderConfig(api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )
    model = provider.models[0]
    snapshot = asyncio.run(provider.submit(
        model,
        VideoEditRequest(
            prompt="将原视频中的唇线笔替换为参考图商品",
            source_video_url="https://assets.example/source.mp4",
            reference_image_urls=("https://assets.example/reference.png",),
            duration_seconds=8,
            aspect_ratio="9:16",
        ),
        VideoProviderContext(project_id="project", shot_index=1, source_asset_name="source.mp4"),
    ))

    assert snapshot.provider_task_id == "thread-1::run-1"
    assert snapshot.status == "queued"
    assert captured_submit["agent_name"] == "pippit_video_part_agent"
    assert captured_submit["asset_ids"] == ["asset-video", "asset-image"]
    tool_param = captured_submit["video_part_tool_param"]
    assert isinstance(tool_param, dict)
    assert tool_param["model"] == "Seedance_2.5"
    assert tool_param["resolution"] == "720p"
    assert tool_param["videos"] == [{"pippit_asset_id": "asset-video"}]
    assert tool_param["images"] == [{"pippit_asset_id": "asset-image"}]


def test_xiaoyunque_refresh_returns_completed_video():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/agent/query_generate_video_result")
        assert json.loads(request.content) == {"thread_id": "thread-1", "run_id": "run-1"}
        return httpx.Response(200, json={
            "ret": "0",
            "log_id": "log-query",
            "data": {
                "run_state": 3,
                "video_urls": ["https://result.example/video.mp4"],
            },
        })

    provider = XiaoyunqueVideoProvider(
        XiaoyunqueProviderConfig(api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )
    snapshot = asyncio.run(provider.refresh(
        provider.models[1],
        "thread-1::run-1",
        VideoProviderContext(project_id="project", shot_index=2),
    ))

    assert snapshot.status == "succeeded"
    assert snapshot.result_url == "https://result.example/video.mp4"
    assert snapshot.request_id == "log-query"


def test_xiaoyunque_models_are_exposed_without_provider_details():
    provider = XiaoyunqueVideoProvider(XiaoyunqueProviderConfig(api_key="test-key"))
    catalog = VideoGenerationRegistry([provider]).catalog("subject_replace")

    assert [item["label"] for item in catalog] == [
        "小云雀 · Seedance 2.5",
        "小云雀 · Seedance 2.0 Mini",
        "小云雀 · Seedance 2.0 Fast",
        "小云雀 · Seedance 2.0",
        "小云雀 · Seedance 2.0 Mini Lite",
    ]
    assert all("provider" not in item for item in catalog)
