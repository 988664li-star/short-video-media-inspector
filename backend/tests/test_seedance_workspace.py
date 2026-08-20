from PIL import Image
import pytest

from backend.app.services.seedance import SeedanceConfigurationError, SeedanceWorkspaceService


ANALYSIS_ID = "a" * 64


def make_service(tmp_path):
    class FakeObjectStorage:
        def ensure_bucket(self):
            return None

    service = SeedanceWorkspaceService(
        tmp_path / "replica_workspaces.sqlite3",
        api_key="",
        api_url="https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks",
        files_api_url="https://ark.cn-beijing.volces.com/api/v3/files",
        file_max_bytes=512 * 1024 * 1024,
        object_storage=FakeObjectStorage(),
    )
    service.initialize()
    return service


def workspace_payload():
    return {
        "model": "doubao-seedance-2-0-mini-260615",
        "extra_instruction": "产品在所有镜头中保持夜灯亮起。",
        "bindings": [{
            "candidate_id": "product_01",
            "enabled": True,
            "assets": [
                {"slot_index": 0, "file_id": "file-product-main", "filename": "product-main.jpg", "label": "产品主图（必传）"},
                {"slot_index": 1, "file_id": "file-product-lit", "filename": "product-lit.jpg", "label": "亮灯/状态图（可选）"},
            ],
        }],
    }


def product_contexts():
    return [{
        "candidate_id": "product_01",
        "source_description": "源视频中的小鸭子夜灯",
        "target_description": "白色鸭形夜灯，胸前有花朵",
        "file_ids": ["file-product-main", "file-product-lit"],
    }]


def test_workspace_persists_ark_file_bindings_and_extra_instruction(tmp_path):
    service = make_service(tmp_path)
    saved = service.save_workspace(ANALYSIS_ID, workspace_payload())

    workspace = saved["workspace"]
    assert workspace["model"] == "doubao-seedance-2-0-mini-260615"
    assert workspace["extra_instruction"] == "产品在所有镜头中保持夜灯亮起。"
    assert workspace["bindings"][0]["assets"][1]["file_id"] == "file-product-lit"
    assert make_service(tmp_path).get_workspace(ANALYSIS_ID)["workspace"] == workspace


def test_prompt_v2_locks_video_context_and_product_identity(tmp_path):
    service = make_service(tmp_path)
    base_prompt = service.prompt_templates.render_video_edit(
        product_contexts(), "产品在所有镜头中保持夜灯亮起。"
    )
    segment_prompt = service.prompt_templates.render_segment_video(base_prompt)
    anchor_prompt = service.prompt_templates.render_anchor_edit(
        {"segment_id": 1}, product_contexts()
    )

    assert "@视频1 是镜头顺序、时长、动作、运镜、人物、背景、构图、光线" in base_prompt
    assert "不得把目标产品参考图、锚点图或文字描述理解为新的场景" in base_prompt
    assert "不得残留源对象的颜色、轮廓、文字、品牌、装饰或结构" in base_prompt
    assert "@图片1 是这个连续片段所有关键镜头合成并完成替换后的最终视觉锚点图" in segment_prompt
    assert "@图片2 是同一连续片段、同一组全部关键镜头的原始拼图" in segment_prompt
    assert "@图片3 及后续图片是目标产品参考图" in segment_prompt
    assert "目标产品未出现的镜头不得凭空加入产品" in segment_prompt
    assert "图2及后续产品参考图只定义目标产品外观" in anchor_prompt
    assert "不得从图1的源产品继承颜色、结构或装饰" in anchor_prompt


def test_anchor_image_size_meets_seedream_minimum_pixel_requirement(tmp_path):
    portrait = tmp_path / "portrait.jpg"
    landscape = tmp_path / "landscape.jpg"
    Image.new("RGB", (9, 16)).save(portrait)
    Image.new("RGB", (16, 9)).save(landscape)

    assert SeedanceWorkspaceService._anchor_image_size(portrait) == "1600x2400"
    assert SeedanceWorkspaceService._anchor_image_size(landscape) == "2400x1600"


def test_accepted_task_without_status_is_queued_not_failed():
    assert SeedanceWorkspaceService._initial_task_status({"id": "cgt-example"}) == "queued"
    assert SeedanceWorkspaceService._initial_task_status(
        {"id": "cgt-example", "status": "running"}
    ) == "running"
    assert SeedanceWorkspaceService._initial_task_status({}) == "failed"


@pytest.mark.asyncio
async def test_generation_review_shows_the_same_segment_prompt_and_submission_assets(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    service.save_workspace(ANALYSIS_ID, workspace_payload())
    monkeypatch.setattr(service, "_load_storyboard_segments", lambda _analysis_id: [{
        "segment_id": 1,
        "start_ms": 0,
        "end_ms": 8770,
        "contact_sheet": "storyboard_chunks/segment_001/storyboard.jpg",
    }])
    monkeypatch.setattr(service, "_selected_product_contexts", lambda _analysis_id, _bindings: product_contexts())
    monkeypatch.setattr(service, "_anchors_by_segment", lambda _analysis_id: {
        1: {"anchor_file_id": "file-anchor-01"},
    })

    async def media(_analysis_id):
        return [{
            "segment_id": 1,
            "start_ms": 0,
            "end_ms": 8770,
            "video_file_id": "file-video-01",
            "contact_sheet_file_id": "file-sheet-01",
            "source_anchor_file_id": "file-source-keyframes-01",
        }]

    async def refresh(_analysis_id, file_id):
        return {
            "id": file_id,
            "filename": f"{file_id}.jpg",
            "mime_type": "video/mp4" if file_id == "file-video-01" else "image/jpeg",
            "download_url": f"https://download.example/{file_id}",
            "status": "active",
            "bytes": 100,
            "expire_at": None,
            "created_at": 0,
            "error": {},
        }

    monkeypatch.setattr(service, "_ensure_segment_media", media)
    monkeypatch.setattr(service, "refresh_file", refresh)

    review = (await service.get_generation_review(ANALYSIS_ID))["segments"][0]

    assert review["segment_id"] == 1
    assert review["source_video"]["id"] == "file-video-01"
    assert review["anchor_image"]["id"] == "file-anchor-01"
    assert review["source_keyframe_image"]["id"] == "file-source-keyframes-01"
    assert review["product_references"][0]["assets"][0]["id"] == "file-product-main"
    assert "请处理完整的 @视频1。它是本次要替换的连续视频片段" in review["prompt"]
    assert "8.77 秒" not in review["prompt"]
    assert "产品在所有镜头中保持夜灯亮起。" in review["prompt"]


@pytest.mark.asyncio
async def test_segment_plan_sends_anchor_and_product_references(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    payload = workspace_payload()
    payload["model"] = "doubao-seedance-2-0-fast-260128"
    service.save_workspace(ANALYSIS_ID, payload)

    async def resolve(_analysis_id, file_id, _label):
        return f"https://download.example/{file_id}"

    async def media(_analysis_id):
        return [{
            "segment_id": 1,
            "start_ms": 0,
            "end_ms": 8770,
            "video_file_id": "file-segment-01",
            "contact_sheet_file_id": "file-sheet-01",
            "source_anchor_file_id": "file-source-keyframes-01",
        }]

    monkeypatch.setattr(service, "_resolve_file_download_url", resolve)
    monkeypatch.setattr(service, "_ensure_segment_media", media)
    monkeypatch.setattr(service, "_source_video_ratio", lambda _analysis_id: "3:4")
    monkeypatch.setattr(service, "_selected_product_contexts", lambda _analysis_id, _bindings: product_contexts())
    monkeypatch.setattr(service, "_anchors_by_segment", lambda _analysis_id: {
        1: {
            "status": "succeeded",
            "model": "doubao-seedream-5-0-260128 [context-lock-v3]",
            "anchor_file_id": "file-segment-anchor-01",
        }
    })

    plan = await service.build_request_plan(ANALYSIS_ID)

    item = plan["segments"][0]
    assert item["segment"] == {"segment_id": 1, "start_ms": 0, "end_ms": 8770}
    content = item["request"]["content"]
    assert item["request"]["model"] == "doubao-seedance-2-0-fast-260128"
    assert item["request"]["duration"] == 9
    assert item["request"]["ratio"] == "3:4"
    assert item["request"]["generate_audio"] is False
    assert item["request"]["watermark"] is False
    assert content[1]["video_url"]["url"] == "https://download.example/file-segment-01"
    assert [item["image_url"]["url"] for item in content[2:]] == [
        "https://download.example/file-segment-anchor-01",
        "https://download.example/file-source-keyframes-01",
        "https://download.example/file-product-main",
        "https://download.example/file-product-lit",
    ]
    assert "@图片1 是这个连续片段所有关键镜头合成并完成替换后的最终视觉锚点图" in content[0]["text"]
    assert "@图片2 是同一连续片段、同一组全部关键镜头的原始拼图" in content[0]["text"]
    assert "@图片3、@图片4 展示的目标产品" in content[0]["text"]


@pytest.mark.asyncio
async def test_user_processed_image_can_be_bound_as_a_segment_anchor(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    payload = workspace_payload()
    service.save_workspace(ANALYSIS_ID, payload)

    async def refresh(_analysis_id, file_id):
        return {
            "id": file_id,
            "filename": "segment-01-processed.jpg",
            "mime_type": "image/jpeg",
        }

    monkeypatch.setattr(service, "refresh_file", refresh)
    saved = await service.bind_anchor_image(ANALYSIS_ID, 1, "file-user-anchor-01")

    anchor = saved["anchors"][0]
    assert anchor["segment_id"] == 1
    assert anchor["status"] == "uploaded"
    assert anchor["anchor_file_id"] == "file-user-anchor-01"
    assert anchor["prompt"] == "用户上传的已处理合并分镜锚点图。"


def test_anchor_preview_shows_the_exact_source_order_and_prompt_without_model_call(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    service.save_workspace(ANALYSIS_ID, workspace_payload())
    segment = {
        "segment_id": 1,
        "start_ms": 0,
        "end_ms": 8770,
        "contact_sheet": "storyboard_chunks/segment_001/storyboard.jpg",
    }
    products = product_contexts()
    monkeypatch.setattr(service, "_load_storyboard_segments", lambda _analysis_id: [segment])
    monkeypatch.setattr(service, "_selected_product_contexts", lambda _analysis_id, _bindings: products)
    monkeypatch.setattr(service, "_analysis_job_path", lambda _analysis_id: tmp_path)
    monkeypatch.setattr(
        service,
        "_ensure_anchor_source_image",
        lambda _analysis_id, _segment: tmp_path / "anchor-input.jpg",
    )

    preview = service.get_anchor_image_previews(ANALYSIS_ID)["previews"][0]

    assert preview["ready"] is True
    assert preview["source_frame_path"] == "anchor-input.jpg"
    assert [item["image_index"] for item in preview["inputs"]] == [1, 2, 3]
    assert preview["inputs"][0]["kind"] == "source_contact_sheet"
    assert preview["inputs"][1]["file_id"] == "file-product-main"
    assert "图1是原视频连续片段 01 的干净多镜头拼图" in preview["prompt"]
    assert "将“源视频中的小鸭子夜灯”替换为产品1" in preview["prompt"]


@pytest.mark.asyncio
async def test_submit_without_key_never_calls_provider_or_creates_billable_task(tmp_path):
    service = make_service(tmp_path)
    service.save_workspace(ANALYSIS_ID, workspace_payload())

    with pytest.raises(SeedanceConfigurationError):
        await service.submit_task(ANALYSIS_ID)

    assert service.get_workspace(ANALYSIS_ID)["tasks"] == []
