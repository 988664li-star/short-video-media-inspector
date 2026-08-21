import pytest

from backend.app.services.canvas_projects import CanvasProjectService
from backend.app.services.canvas_projects.video import CanvasVideoService


class FakeDetector:
    def detect(self, _: str, __: object) -> dict:
        return {
            "duration_seconds": 3.0,
            "shots": [
                {"index": 1, "start_seconds": 0.0, "end_seconds": 1.2, "duration_seconds": 1.2},
                {"index": 2, "start_seconds": 1.2, "end_seconds": 3.0, "duration_seconds": 1.8},
            ],
        }


class FakeExporter:
    def export(self, _: object, directory: object, shots: list[dict]) -> None:
        for shot in shots:
            scene = directory / f"scene_{shot['index']:03d}"
            selected = scene / "selected"
            selected.mkdir(parents=True)
            (scene / "video.mp4").write_bytes(f"clip-{shot['index']}".encode())
            frame = selected / "frame_01_50.jpg"
            frame.write_bytes(f"frame-{shot['index']}".encode())
            shot["clip"] = f"scene_{shot['index']:03d}/video.mp4"
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
    return projects, service, project


@pytest.mark.asyncio
async def test_split_by_shots_persists_each_clip_as_canvas_asset(tmp_path):
    projects, service, project = make_service(tmp_path)
    source = projects.save_asset(project["id"], "source.mp4", "video/mp4", b"source")

    result = await service.split_by_shots(project["id"], source["id"])

    assert [shot["duration_seconds"] for shot in result["shots"]] == [1.2, 1.8]
    assert [shot["asset"]["filename"] for shot in result["shots"]] == [
        "source-shot-01.mp4", "source-shot-02.mp4",
    ]
    assert len(projects.list_assets(project["id"])) == 3


@pytest.mark.asyncio
async def test_extract_keyframes_persists_image_assets(tmp_path):
    projects, service, project = make_service(tmp_path)
    source = projects.save_asset(project["id"], "source.mp4", "video/mp4", b"source")

    result = await service.extract_keyframes(project["id"], source["id"])

    assert [frame["shot_index"] for frame in result["frames"]] == [1, 2]
    assert all(frame["asset"]["mime_type"] == "image/jpeg" for frame in result["frames"])
    assert len(projects.list_assets(project["id"])) == 3
