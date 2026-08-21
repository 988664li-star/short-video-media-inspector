from backend.app.services.canvas_projects import CanvasProjectService
from backend.app.schemas.requests import CanvasProjectUpdateRequest


def test_canvas_project_is_persisted_with_an_empty_document_and_local_assets(tmp_path):
    service = CanvasProjectService(
        tmp_path / "canvas_projects.sqlite3",
        tmp_path / "canvas_projects",
    )
    service.initialize()

    created = service.create_project("商品替换测试")
    assert created["nodes"] == []
    assert created["edges"] == []
    assert created["viewport"] == {"x": 0, "y": 0, "scale": 0.9}
    assert (tmp_path / "canvas_projects" / created["id"] / "assets").is_dir()
    assert service.list_projects() == [{
        "id": created["id"],
        "name": "商品替换测试",
        "asset_directory": f"{created['id']}/assets",
        "created_at": created["created_at"],
        "updated_at": created["updated_at"],
    }]

    saved = service.update_project(created["id"], {
        "name": "商品替换测试 2",
        "nodes": [{
            "id": "image-1",
            "kind": "image",
            "x": 320,
            "y": 180,
            "title": "商品图",
            "detail": "本地素材",
            "content": "",
            "operation": {
                "prompt": "把商品放在柔和的室内光线下",
                "model": "doubao-seedream-5-0-260128",
                "source_url": "",
                "status": "idle",
                "error": "",
            },
        }],
        "edges": [{
            "id": "edge-1",
            "source": "image-1",
            "target": "image-2",
            "sourceHandle": "output",
            "targetHandle": "input",
        }],
        "viewport": {"x": 52, "y": 33, "scale": 0.8},
    })
    assert saved["name"] == "商品替换测试 2"
    assert saved["nodes"][0]["id"] == "image-1"
    assert saved["nodes"][0]["operation"]["prompt"] == "把商品放在柔和的室内光线下"
    assert saved["edges"][0]["target"] == "image-2"
    assert service.get_project(created["id"])["viewport"]["scale"] == 0.8

    asset = service.save_asset(created["id"], "product.png", "image/png", b"asset-bytes")
    restored_asset, path = service.get_asset_file(created["id"], asset["id"])
    assert restored_asset["filename"] == "product.png"
    assert path.read_bytes() == b"asset-bytes"


def test_default_canvas_is_created_once(tmp_path):
    service = CanvasProjectService(
        tmp_path / "canvas_projects.sqlite3",
        tmp_path / "canvas_projects",
    )
    service.initialize()

    first = service.get_or_create_default_project()
    second = service.get_or_create_default_project()

    assert first["id"] == second["id"]
    assert len(service.list_projects()) == 1


def test_shot_collection_node_keeps_all_local_shot_assets():
    request = CanvasProjectUpdateRequest.model_validate({
        "name": "分镜测试",
        "nodes": [{
            "id": "shot-group-1",
            "kind": "shot_collection",
            "x": 480,
            "y": 200,
            "title": "分镜组 · 2 个镜头",
            "detail": "完整保留 2 个连续镜头",
            "content": "",
            "source_node_id": "video-1",
            "derived_kind": "shot",
            "reference_assets": [{
                "id": "c" * 32,
                "url": "/api/canvas/projects/project/assets/" + "c" * 32,
                "filename": "product-reference.png",
                "mime_type": "image/png",
            }],
            "shot_assets": [{
                "index": 1,
                "start_seconds": 0,
                "end_seconds": 2.5,
                "duration_seconds": 2.5,
                "asset_id": "a" * 32,
                "asset_url": "/api/canvas/projects/project/assets/" + "a" * 32,
                "asset_name": "shot-01.mp4",
            }, {
                "index": 2,
                "start_seconds": 2.5,
                "end_seconds": 5,
                "duration_seconds": 2.5,
                "asset_id": "b" * 32,
                "asset_url": "/api/canvas/projects/project/assets/" + "b" * 32,
                "asset_name": "shot-02.mp4",
            }],
        }],
        "edges": [],
        "viewport": {"x": 0, "y": 0, "scale": 0.9},
    })

    assert request.nodes[0].kind == "shot_collection"
    assert [shot.asset_name for shot in request.nodes[0].shot_assets] == ["shot-01.mp4", "shot-02.mp4"]
    assert request.nodes[0].reference_assets[0].filename == "product-reference.png"


def test_replacement_analysis_and_task_nodes_persist_their_shot_level_prompt_data():
    request = CanvasProjectUpdateRequest.model_validate({
        "name": "逐镜头替换",
        "nodes": [{
            "id": "analysis-1",
            "kind": "replaceable_analysis",
            "x": 600,
            "y": 160,
            "title": "可替换对象 · 1 项",
            "detail": "已完成识别",
            "content": "",
            "source_node_id": "shot-group-1",
            "analysis_keyframes": [{
                "shot_index": 1,
                "asset_id": "a" * 32,
                "asset_url": "/api/canvas/projects/project/assets/" + "a" * 32,
                "asset_name": "shot-01-analysis-frame.jpg",
            }],
            "replaceable_objects": [{
                "id": "object-1",
                "kind": "product",
                "name": "深色编织托盘",
                "description": "桌面上的矩形托盘",
                "shot_indices": [1, 2],
                "actions": [{"shot_index": 1, "description": "桌面静态展示"}],
            }],
        }, {
            "id": "task-1",
            "kind": "replacement_task",
            "x": 1000,
            "y": 160,
            "title": "商品替换 · 深色编织托盘",
            "detail": "覆盖 2 个镜头",
            "content": "",
            "replacement_task": {
                "analysis_node_id": "analysis-1",
                "shot_collection_node_id": "shot-group-1",
                "source_object_id": "object-1",
                "source_object_kind": "product",
                "source_object_name": "深色编织托盘",
                "source_object_description": "桌面上的矩形托盘",
                "shot_indices": [1, 2],
                "actions": [{"shot_index": 1, "description": "桌面静态展示"}],
                "target_description": "浅色木质托盘",
                "shot_prompts": [{"shot_index": 1, "prompt": "替换当前镜头中的托盘", "status": "ready"}],
            },
        }],
        "edges": [{"id": "edge-1", "source": "analysis-1", "target": "task-1"}],
        "viewport": {"x": 0, "y": 0, "scale": 0.9},
    })

    analysis, task = request.nodes
    assert analysis.replaceable_objects[0].name == "深色编织托盘"
    assert task.replacement_task.shot_prompts[0].status == "ready"
