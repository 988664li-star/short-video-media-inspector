import pytest

from backend.app.services.canvas_projects import CanvasProjectService
from backend.app.services.canvas_projects.video import CanvasVideoError, CanvasVideoService


class FakeDetector:
    def detect(self, _: str, __: object) -> dict:
        return {
            "duration_seconds": 5.0,
            "shots": [
                {"index": 1, "start_seconds": 0.0, "end_seconds": 1.2, "duration_seconds": 1.2},
                {"index": 2, "start_seconds": 1.2, "end_seconds": 5.0, "duration_seconds": 3.8},
            ],
        }


class FakeExporter:
    def export(
        self, _: object, directory: object, shots: list[dict], *, extract_keyframes: bool = True
    ) -> None:
        for shot in shots:
            scene = directory / f"scene_{shot['index']:03d}"
            selected = scene / "selected"
            selected.mkdir(parents=True)
            (scene / "video.mp4").write_bytes(f"clip-{shot['index']}".encode())
            shot["clip"] = f"scene_{shot['index']:03d}/video.mp4"
            if extract_keyframes:
                frame = selected / "frame_01_50.jpg"
                frame.write_bytes(f"frame-{shot['index']}".encode())
                shot["selected_frames"] = [{
                    "timestamp_seconds": shot["start_seconds"] + 0.5,
                    "path": f"scene_{shot['index']:03d}/selected/frame_01_50.jpg",
                }]


def make_service(tmp_path) -> tuple[CanvasProjectService, CanvasVideoService, dict]:
    projects = CanvasProjectService(tmp_path / "canvas.sqlite3", tmp_path / "canvas")
    projects.initialize()
    project = projects.create_project("视频能力测试")
    service = CanvasVideoService(
        projects,
        ffmpeg_binary="ffmpeg",
        scene_threshold=30,
        min_shot_seconds=.4,
        max_asset_bytes=1024,
    )
    service.detector = FakeDetector()
    service.exporter = FakeExporter()
    service._video_duration = lambda _: 5.0  # type: ignore[method-assign]
    return projects, service, project


@pytest.mark.asyncio
async def test_split_by_shots_persists_each_clip_as_canvas_asset(tmp_path):
    projects, service, project = make_service(tmp_path)
    source = projects.save_asset(project["id"], "source.mp4", "video/mp4", b"source")

    result = await service.split_by_shots(project["id"], source["id"])

    assert [shot["duration_seconds"] for shot in result["shots"]] == [5.0]
    assert [shot["asset"]["filename"] for shot in result["shots"]] == [
        "source-edit-segment-01.mp4",
    ]
    assert len(projects.list_assets(project["id"])) == 2


@pytest.mark.asyncio
async def test_extract_keyframes_persists_image_assets(tmp_path):
    projects, service, project = make_service(tmp_path)
    source = projects.save_asset(project["id"], "source.mp4", "video/mp4", b"source")

    result = await service.extract_keyframes(project["id"], source["id"])

    assert [frame["shot_index"] for frame in result["frames"]] == [1, 2]
    assert all(frame["asset"]["mime_type"] == "image/jpeg" for frame in result["frames"])
    assert len(projects.list_assets(project["id"])) == 3


def test_plan_generation_shots_uses_continuous_eight_second_edit_spans():
    shots = CanvasVideoService._plan_generation_shots(16.0)

    assert [(shot["start_seconds"], shot["end_seconds"]) for shot in shots] == [
        (0.0, 8.0), (8.0, 16.0),
    ]
    assert all(4 <= shot["duration_seconds"] <= 8 for shot in shots)


def test_plan_generation_shots_rejects_video_shorter_than_seedance_minimum():
    with pytest.raises(CanvasVideoError, match="短于 Seedance 最短"):
        CanvasVideoService._plan_generation_shots(3.9)
