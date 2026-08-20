from backend.app.services.replica_projects import ReplicaProjectService


def project_payload():
    return {
        "name": "夏季清凉喷雾测试",
        "product_name": "便携空调清凉喷雾",
        "platform": "douyin",
        "market": "中国大陆",
        "audience": "夏季通勤和宿舍人群",
        "landing_page": "https://example.com/product",
        "target_cpa": 80,
        "brand_facts": "清凉喷雾，单瓶 39 元，适合通勤使用。",
        "prohibited_claims": "治疗，保证有效",
        "rights_mode": "structure",
        "rights_confirmed": True,
        "aigc_label_required": True,
    }


def test_replica_project_can_be_created_updated_and_restored(tmp_path):
    service = ReplicaProjectService(tmp_path / "replica_projects.sqlite3")
    service.initialize()

    saved = service.save_project(project_payload())
    assert saved["id"]
    assert saved["target_cpa"] == 80
    assert service.list_projects() == [saved]

    updated = service.save_project(
        {**project_payload(), "name": "夏季清凉喷雾第二轮"}, saved["id"]
    )
    assert updated["id"] == saved["id"]
    assert updated["name"] == "夏季清凉喷雾第二轮"
    assert len(service.list_projects()) == 1

    restored = ReplicaProjectService(tmp_path / "replica_projects.sqlite3")
    restored.initialize()
    assert restored.list_projects()[0]["name"] == "夏季清凉喷雾第二轮"
