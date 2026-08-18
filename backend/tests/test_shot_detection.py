import shutil

import av
import numpy as np
import pytest

from backend.app.services.media import MediaResource
from backend.app.services.shot_detection import (
    ShotDetectionConfig,
    ShotDetectionService,
)


def _create_two_shot_video(path):
    container = av.open(str(path), "w")
    stream = container.add_stream("mpeg4", rate=8)
    stream.width = 64
    stream.height = 64
    stream.pix_fmt = "yuv420p"
    for color in ((255, 0, 0), (0, 0, 255)):
        frame_data = np.full((64, 64, 3), color, dtype=np.uint8)
        for _ in range(16):
            frame = av.VideoFrame.from_ndarray(frame_data, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def _service(tmp_path):
    return ShotDetectionService(
        ShotDetectionConfig(
            data_path=tmp_path / "shot_detection",
            max_media_bytes=10 * 1024 * 1024,
            scene_threshold=5,
            min_shot_seconds=0.5,
            cache_ttl_seconds=3600,
            ffmpeg_binary="ffmpeg",
        )
    )


def test_detect_file_splits_a_known_hard_cut(tmp_path):
    source_path = tmp_path / "two-shots.mp4"
    _create_two_shot_video(source_path)

    result = _service(tmp_path)._detect_file("1234567890123456789", source_path)

    assert result["duration_seconds"] == pytest.approx(4, abs=0.2)
    assert len(result["shots"]) == 2
    assert result["detector"] == "PySceneDetect ContentDetector"
    assert result["shots"][0]["start_seconds"] == 0
    assert result["shots"][0]["end_seconds"] == pytest.approx(2, abs=0.3)
    assert result["shots"][1]["cut_score"] is None


@pytest.mark.asyncio
async def test_detect_persists_source_and_result_in_one_job_directory(tmp_path, monkeypatch):
    original_source = tmp_path / "source.mp4"
    _create_two_shot_video(original_source)
    service = _service(tmp_path)
    download_count = 0

    async def copy_source(resource, destination):
        nonlocal download_count
        download_count += 1
        shutil.copyfile(original_source, destination)

    monkeypatch.setattr(service, "_download_video", copy_source)
    resource = MediaResource(
        source_url="https://cdn.example/source.mp4",
        headers={},
        kind="video",
    )

    result = await service.detect("1234567890123456789", resource)
    cached = await service.detect("1234567890123456789", resource)

    job_paths = list((tmp_path / "shot_detection").iterdir())
    assert len(job_paths) == 1
    assert (job_paths[0] / "source.mp4").is_file()
    assert (job_paths[0] / "scenes.json").is_file()
    assert result["shots"][0]["clip"].startswith("scene_001/")
    assert result["shots"][0]["selected_frames"]
    first_frame = result["shots"][0]["selected_frames"][0]["path"]
    assert service.get_scene_asset(result["analysis_id"], first_frame).is_file()
    assert service.get_scene_asset(result["analysis_id"], "../source.mp4") is None
    assert result["cached"] is False
    assert cached["cached"] is True
    assert download_count == 1
