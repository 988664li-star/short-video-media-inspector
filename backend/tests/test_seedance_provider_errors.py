from backend.app.services.seedance.workspace import SeedanceWorkspaceService


def test_seedream_provider_error_is_named_for_the_image_provider():
    message = SeedanceWorkspaceService._provider_error_message(
        {"message": "上游暂不可用"},
        502,
        provider="Seedream 5.0 图片编辑接口",
    )

    assert message == "Seedream 5.0 图片编辑接口 返回 502：上游暂不可用"
