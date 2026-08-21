import pytest

from backend.app.services.canvas_projects.replacement import (
    CanvasReplacementAnalysisError,
    CanvasReplacementAnalysisService,
)
from backend.app.services.canvas_projects.prompts import CanvasPromptTemplates
from backend.app.services.canvas_projects.replacement_tasks import (
    CanvasReplacementTaskService,
    CanvasReplacementVideoConfig,
)


def test_normalise_replacement_objects_requires_numeric_shot_indices():
    objects = CanvasReplacementAnalysisService._normalise_objects({
        "objects": [{
            "kind": "product",
            "name": "托盘",
            "description": "视频持续展示的主商品",
            "shot_indices": [1, 2, 20],
            "actions": [{
                "shot_index": 1,
                "description": "手持展示托盘正面。",
            }],
        }],
    }, {1, 2, 20})

    assert objects == [{
        "id": "object-1",
        "kind": "product",
        "name": "托盘",
        "description": "视频持续展示的主商品",
        "shot_indices": [1, 2, 20],
        "actions": [
            {"shot_index": 1, "description": "手持展示托盘正面。"},
            {"shot_index": 2, "description": "托盘 出现在当前连续片段中，保持原有位置、动作与遮挡关系。"},
            {"shot_index": 20, "description": "托盘 出现在当前连续片段中，保持原有位置、动作与遮挡关系。"},
        ],
    }]


def test_normalise_replacement_objects_limits_results_to_three_primary_subjects():
    objects = CanvasReplacementAnalysisService._normalise_objects({
        "objects": [
            {"kind": "product", "name": f"主体 {index}", "shot_indices": [1]}
            for index in range(1, 5)
        ],
    }, {1})

    assert [item["name"] for item in objects] == ["主体 1", "主体 2", "主体 3"]


def test_normalise_replacement_objects_rejects_non_numeric_shot_indices():
    with pytest.raises(CanvasReplacementAnalysisError, match="必须使用整数镜头号"):
        CanvasReplacementAnalysisService._normalise_objects({
            "objects": [{"kind": "product", "name": "托盘", "shot_indices": ["SHOT01"]}],
        }, {1})


def test_per_shot_video_prompt_uses_the_external_template_and_numeric_shot_actions(tmp_path):
    templates = CanvasPromptTemplates.load()
    service = CanvasReplacementTaskService(
        project_service=None,  # type: ignore[arg-type] - prompt rendering needs no local asset access.
        object_storage=None,  # type: ignore[arg-type] - prompt rendering needs no object storage.
        config=CanvasReplacementVideoConfig(
            api_key="", api_url="https://example.invalid/tasks", max_asset_bytes=1
        ),
        prompt_templates=templates,
    )

    prompts = service.build_prompts(
        source_object_name="木质托盘",
        source_object_description="原视频反复展示的深色木质托盘",
        target_description="浅米白大理石纹、香槟金边框与双侧提手托盘",
        target_asset_ids=["a" * 32],
        shots=[{
            "index": 3, "start_seconds": 2, "end_seconds": 3, "duration_seconds": 1,
            "asset_id": "b" * 32, "asset_url": "/asset", "asset_name": "shot-03.mp4",
        }],
        actions=[{"shot_index": 3, "description": "画面中有 2 个托盘：左侧平放桌面，右侧被手持展示。"}],
    )

    assert len(prompts) == 1
    assert prompts[0]["status"] == "ready"
    assert prompts[0]["input_revision"] == 3
    assert "@视频1" in prompts[0]["prompt"]
    assert "@图片1" in prompts[0]["prompt"]
    assert "@图片2" not in prompts[0]["prompt"]
    assert "画面中有 2 个托盘" in prompts[0]["prompt"]
    assert "浅米白大理石纹" in prompts[0]["prompt"]
    assert "保留原视频已有的字幕" in prompts[0]["prompt"]
    assert "逐一一对一替换" in prompts[0]["prompt"]


def test_replacement_request_uses_one_video_and_target_references():
    content = CanvasReplacementTaskService._request_content(
        "替换提示词",
        "https://example.invalid/source.mp4",
        ["https://example.invalid/product-a.jpg", "https://example.invalid/product-b.jpg"],
    )

    assert content[0] == {"type": "text", "text": "替换提示词"}
    assert content[1]["type"] == "video_url"
    assert content[1]["video_url"]["url"].endswith("source.mp4")
    assert [item["image_url"]["url"] for item in content[2:]] == [
        "https://example.invalid/product-a.jpg",
        "https://example.invalid/product-b.jpg",
    ]
