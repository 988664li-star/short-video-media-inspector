import asyncio
import base64

import pytest

from backend.app.services.canvas_projects import (
    CanvasAIConfig,
    CanvasAIError,
    CanvasAIService,
    CanvasProjectService,
)


class FakeTextClient:
    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    async def complete_json(self, **request):
        self.request = request
        return {"content": "这是模型生成并回填的正文。"}, {"total_tokens": 32}


def make_service(tmp_path, *, image_api_key="test-key"):
    project_service = CanvasProjectService(
        tmp_path / "canvas_projects.sqlite3",
        tmp_path / "canvas_projects",
    )
    project_service.initialize()
    text_client = FakeTextClient()
    ai_service = CanvasAIService(
        project_service,
        text_client,
        CanvasAIConfig(
            image_api_key=image_api_key,
            image_api_url="https://example.com/images/generations",
            image_model="doubao-seedream-5-0-260128",
            text_model="Qwen/Qwen3.6-27B",
        ),
    )
    return project_service, text_client, ai_service


def test_text_node_combines_prompt_and_upstream_context(tmp_path):
    _, text_client, ai_service = make_service(tmp_path)

    result = asyncio.run(ai_service.generate_text("写一段商品文案", "上游产品图：花朵灯"))

    assert result == {
        "content": "这是模型生成并回填的正文。",
        "model": "Qwen/Qwen3.6-27B",
    }
    assert text_client.request is not None
    assert "写一段商品文案" in str(text_client.request["content"])
    assert "上游产品图：花朵灯" in str(text_client.request["content"])


def test_image_node_collects_url_and_local_image_references(tmp_path):
    project_service, _, ai_service = make_service(tmp_path)
    project = project_service.create_project("图片生成测试")
    asset = project_service.save_asset(project["id"], "product.png", "image/png", b"image-bytes")

    references = asyncio.run(ai_service._reference_images(
        project["id"],
        "https://example.com/reference.png",
        [asset["id"], asset["id"]],
    ))

    assert references[0] == "https://example.com/reference.png"
    assert references[1] == "data:image/png;base64," + base64.b64encode(b"image-bytes").decode("ascii")
    assert len(references) == 2


def test_image_node_rejects_invalid_reference_url_before_model_request(tmp_path):
    project_service, _, ai_service = make_service(tmp_path)
    project = project_service.create_project("图片生成测试")

    with pytest.raises(CanvasAIError, match="HTTP 或 HTTPS"):
        asyncio.run(ai_service.generate_image(project["id"], "生成产品图", "file:///tmp/a.png", []))

