from pathlib import Path

import av
import numpy as np

from backend.app.services.storyboard.chunks import (
    StoryboardChunkConfig,
    StoryboardChunkService,
)


def _create_video(path: Path) -> None:
    container = av.open(str(path), "w")
    stream = container.add_stream("mpeg4", rate=8)
    stream.width = 64
    stream.height = 64
    stream.pix_fmt = "yuv420p"
    for _ in range(16):
        frame = av.VideoFrame.from_ndarray(
            np.full((64, 64, 3), (30, 160, 220), dtype=np.uint8), format="rgb24"
        )
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def test_missing_keyframe_is_rebuilt_from_local_reference_video(tmp_path: Path):
    _create_video(tmp_path / "source.mp4")
    service = StoryboardChunkService(
        StoryboardChunkConfig(data_path=tmp_path, ffmpeg_binary="ffmpeg")
    )
    output = tmp_path / "storyboard_chunks" / "segment_001" / "storyboard.jpg"
    missing_frame = "scene_001/selected/frame_01_50.jpg"

    service._render_contact_sheet(
        tmp_path,
        output,
        [
            {
                "order": 1,
                "start_ms": 0,
                "end_ms": 2000,
                "forced_split": False,
                "frame_paths": [missing_frame],
            }
        ],
    )

    assert (tmp_path / missing_frame).is_file()
    assert output.is_file()


def test_keyframe_recovery_clamps_a_timestamp_beyond_the_video_tail(tmp_path: Path):
    source = tmp_path / "source.mp4"
    _create_video(source)
    service = StoryboardChunkService(
        StoryboardChunkConfig(data_path=tmp_path, ffmpeg_binary="ffmpeg")
    )
    output = tmp_path / "scene_001" / "selected" / "tail.jpg"

    service._extract_frame(source, output, seconds=99)

    assert output.is_file()
