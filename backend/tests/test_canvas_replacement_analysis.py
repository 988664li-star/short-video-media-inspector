from backend.app.services.canvas_projects.replacement import (
    CanvasReplacementAnalysisError,
    CanvasReplacementAnalysisService,
)
from backend.app.services.canvas_projects.prompts import CanvasPromptTemplates
from backend.app.services.canvas_projects.replacement_tasks import (
    CanvasReplacementTaskService,
    CanvasReplacementVideoConfig,
)
from backend.app.services.video_generation.providers import SeedanceVideoProvider


def test_single_shot_observations_use_server_shot_index_and_require_frame_evidence():
    observations = CanvasReplacementAnalysisService._normalise_shot_observations({
        "objects": [{
            "kind": "product",
            "name": "米色唇线笔",
            "description": "用于勾勒唇部轮廓",
            "action": "帧 1 至帧 4 中被手持使用。",
            "shot_indices": [1, 2, 99],
        }, {
            "kind": "product",
            "name": "没有证据的工具",
            "description": "无法确认",
            "action": "画面中可能出现。",
        }],
    }, 2)

    assert observations == [{
        "observation_id": "shot-2-object-1",
        "shot_index": 2,
        "kind": "product",
        "name": "米色唇线笔",
        "description": "用于勾勒唇部轮廓",
        "action": "帧 1 至帧 4 中被手持使用。",
    }]


def test_single_shot_observations_do_not_limit_results_to_three_subjects():
    observations = CanvasReplacementAnalysisService._normalise_shot_observations({
        "objects": [
            {
                "kind": "product",
                "name": f"主体 {index}",
                "description": "具有独立替换价值",
                "action": "帧 1 中清晰出现。",
            }
            for index in range(1, 5)
        ],
    }, 1)

    assert [item["name"] for item in observations] == ["主体 1", "主体 2", "主体 3", "主体 4"]


def test_merge_cannot_combine_visually_verified_but_different_products():
    observations = [
        {
            "observation_id": "shot-1-object-1", "shot_index": 1, "kind": "product",
            "name": "黑色唇部修边工具", "description": "清理唇线边缘", "action": "帧 3 中出现。",
        },
        {
            "observation_id": "shot-2-object-1", "shot_index": 2, "kind": "product",
            "name": "米色唇线笔", "description": "勾勒唇部轮廓", "action": "帧 1 中出现。",
        },
    ]

    objects = CanvasReplacementAnalysisService._merge_observations({
        "groups": [{
            "observation_ids": ["shot-1-object-1", "shot-2-object-1"],
            "kind": "product",
            "name": "唇部化妆工具",
            "description": "错误地把两个产品合并",
        }],
    }, observations)

    assert [(item["name"], item["shot_indices"]) for item in objects] == [
        ("黑色唇部修边工具", [1]),
        ("米色唇线笔", [2]),
    ]


def test_per_shot_video_prompt_uses_the_external_template_and_numeric_shot_actions(tmp_path):
    templates = CanvasPromptTemplates.load()
    service = CanvasReplacementTaskService(
        project_service=None,  # type: ignore[arg-type] - prompt rendering needs no local asset access.
        object_storage=None,  # type: ignore[arg-type] - prompt rendering needs no object storage.
        config=CanvasReplacementVideoConfig(max_asset_bytes=1),
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


def test_one_prompt_maps_multiple_source_subjects_to_ordered_target_images():
    service = CanvasReplacementTaskService(
        project_service=None,  # type: ignore[arg-type] - prompt rendering needs no local asset access.
        object_storage=None,  # type: ignore[arg-type] - prompt rendering needs no object storage.
        config=CanvasReplacementVideoConfig(max_asset_bytes=1),
        prompt_templates=CanvasPromptTemplates.load(),
    )
    shoe_asset_id = "a" * 32
    sock_asset_id = "b" * 32

    prompts = service.build_prompts(
        source_object_name="白色运动鞋",
        source_object_description="人物脚上的白色运动鞋",
        target_description="",
        target_asset_ids=[shoe_asset_id, sock_asset_id],
        shots=[{
            "index": 1, "start_seconds": 0, "end_seconds": 6, "duration_seconds": 6,
            "asset_id": "c" * 32, "asset_url": "/asset", "asset_name": "shot-01.mp4",
        }],
        actions=[],
        subjects=[
            {
                "source_object_id": "object-shoes",
                "source_object_kind": "product",
                "source_object_name": "白色运动鞋",
                "source_object_description": "人物脚上的白色运动鞋",
                "shot_indices": [1],
                "actions": [{"shot_index": 1, "description": "运动鞋随脚步移动。"}],
                "target_description": "目标运动鞋的颜色和结构以参考图为准",
                "target_asset_ids": [shoe_asset_id],
            },
            {
                "source_object_id": "object-socks",
                "source_object_kind": "product",
                "source_object_name": "卡通图案袜子",
                "source_object_description": "人物穿着的短袜",
                "shot_indices": [1],
                "actions": [{"shot_index": 1, "description": "袜子与运动鞋保持穿戴关系。"}],
                "target_description": "目标袜子的卡通图案以参考图为准",
                "target_asset_ids": [sock_asset_id],
            },
        ],
    )

    assert len(prompts) == 1
    prompt = prompts[0]["prompt"]
    assert "白色运动鞋" in prompt
    assert "@图片1 所示的目标对象" in prompt
    assert "卡通图案袜子" in prompt
    assert "@图片2 所示的目标对象" in prompt
    assert "一次完成全部替换" in prompt


def test_replacement_request_uses_one_video_and_target_references():
    content = SeedanceVideoProvider.request_content(
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


def test_replacement_analysis_includes_source_caption_for_visual_disambiguation():
    service = CanvasReplacementAnalysisService(
        project_service=None,  # type: ignore[arg-type] - no keyframe files are read.
        vision_client=None,  # type: ignore[arg-type] - prompt construction needs no client.
    )

    content = service._vision_content(
        "project",
        [],
        "识别可替换主体。",
        "You only need ONE lip pencil!! 可爱心唇の作り方",
    )

    assert "来源作品标题/发布文案" in content[0]["text"]
    assert "lip pencil" in content[0]["text"]
