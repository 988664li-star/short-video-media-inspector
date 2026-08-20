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
        "prompt": "只替换 @image_1 指向的产品。",
        "bindings": [{
            "candidate_id": "product_01",
            "enabled": True,
            "assets": [
                {"slot_index": 0, "file_id": "file-product-main", "filename": "product-main.jpg", "label": "产品主图（必传）"},
                {"slot_index": 1, "file_id": "file-product-lit", "filename": "product-lit.jpg", "label": "亮灯/状态图（可选）"},
            ],
        }],
    }


def test_workspace_persists_ark_file_bindings_and_prompt(tmp_path):
    service = make_service(tmp_path)
    saved = service.save_workspace(ANALYSIS_ID, workspace_payload())

    workspace = saved["workspace"]
    assert workspace["model"] == "doubao-seedance-2-0-mini-260615"
    assert workspace["bindings"][0]["assets"][1]["file_id"] == "file-product-lit"
    assert make_service(tmp_path).get_workspace(ANALYSIS_ID)["workspace"] == workspace


@pytest.mark.asyncio
async def test_segment_plan_uses_one_merged_anchor_as_its_only_reference_image(tmp_path, monkeypatch):
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
        }]

    monkeypatch.setattr(service, "_resolve_file_download_url", resolve)
    monkeypatch.setattr(service, "_ensure_segment_media", media)
    monkeypatch.setattr(service, "_anchors_by_segment", lambda _analysis_id: {
        1: {
            "status": "succeeded",
                "model": "gpt-image-2 [clean-montage-v2]",
            "anchor_file_id": "file-segment-anchor-01",
        }
    })

    plan = await service.build_request_plan(ANALYSIS_ID)

    item = plan["segments"][0]
    assert item["segment"] == {"segment_id": 1, "start_ms": 0, "end_ms": 8770}
    content = item["request"]["content"]
    assert item["request"]["model"] == "doubao-seedance-2-0-fast-260128"
    assert item["request"]["duration"] == -1
    assert item["request"]["ratio"] == "adaptive"
    assert item["request"]["generate_audio"] is False
    assert item["request"]["watermark"] is False
    assert content[1]["video_url"]["url"] == "https://download.example/file-segment-01"
    assert content[-1]["image_url"]["url"] == "https://download.example/file-segment-anchor-01"
    assert "@图片1 是该分段全部镜头合并后的最终视觉锚点图" in content[0]["text"]


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
    products = [{
        "candidate_id": "product_01",
        "source_description": "源视频中的小鸭子夜灯",
        "target_description": "白色鸭形夜灯，胸前有花朵",
        "file_ids": ["file-product-main", "file-product-lit"],
    }]
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
    assert "图1是原视频分段 01 的干净多镜头拼图" in preview["prompt"]
    assert "将“源视频中的小鸭子夜灯”替换为产品1" in preview["prompt"]


@pytest.mark.asyncio
async def test_submit_without_key_never_calls_provider_or_creates_billable_task(tmp_path):
    service = make_service(tmp_path)
    service.save_workspace(ANALYSIS_ID, workspace_payload())

    with pytest.raises(SeedanceConfigurationError):
        await service.submit_task(ANALYSIS_ID)

    assert service.get_workspace(ANALYSIS_ID)["tasks"] == []
