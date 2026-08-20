import pytest

from backend.app.services.shot_detection.errors import ShotDecodeError
from backend.app.services.shot_detection.exporter import SceneAssetExporter


def test_keyframe_timestamp_never_exceeds_last_decodable_source_frame():
    timestamp = SceneAssetExporter._frame_timestamp(
        start_seconds=83.5,
        duration_seconds=2.0,
        position=0.8,
        source_duration=84.27,
    )

    assert timestamp == 84.17


def test_frame_export_reports_missing_output_immediately(tmp_path, monkeypatch):
    exporter = SceneAssetExporter("ffmpeg")
    monkeypatch.setattr(exporter, "_run_ffmpeg", lambda _arguments: None)

    with pytest.raises(ShotDecodeError, match="FFmpeg 未导出关键帧"):
        exporter._export_frame(
            tmp_path / "source.mp4", tmp_path / "missing.jpg", 12.34, quality=2
        )
