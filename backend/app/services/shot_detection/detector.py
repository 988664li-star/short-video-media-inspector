"""PySceneDetect boundary detection for one local source video."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.services.shot_detection.errors import ShotDecodeError


class PySceneDetector:
    """Detect hard visual cuts with PySceneDetect's content detector."""

    def __init__(self, threshold: float, min_shot_seconds: float) -> None:
        self.threshold = threshold
        self.min_shot_seconds = min_shot_seconds

    def detect(self, aweme_id: str, source_path: Path) -> dict[str, Any]:
        try:
            from scenedetect import SceneManager, open_video
            from scenedetect.detectors import ContentDetector
        except ImportError as exc:
            raise ShotDecodeError("缺少 PySceneDetect 分镜依赖，请重新安装后端依赖") from exc
        try:
            video = open_video(str(source_path))
        except Exception as exc:
            raise ShotDecodeError(f"无法打开视频文件：{exc}") from exc

        scene_manager = SceneManager()
        frame_rate = float(video.frame_rate)
        min_scene_len = max(1, round(frame_rate * self.min_shot_seconds))
        scene_manager.add_detector(
            ContentDetector(threshold=self.threshold, min_scene_len=min_scene_len)
        )
        try:
            scene_manager.detect_scenes(video=video, show_progress=False)
            scenes = scene_manager.get_scene_list(start_in_scene=True)
        except Exception as exc:
            raise ShotDecodeError(f"PySceneDetect 镜头识别失败：{exc}") from exc
        finally:
            close = getattr(video, "close", None)
            if callable(close):
                close()

        shots = self._serialize_scenes(scenes)
        duration = shots[-1]["end_seconds"] if shots else 0.0
        return {
            "aweme_id": aweme_id,
            "duration_seconds": round(duration, 2),
            "fps": frame_rate,
            "detector": "PySceneDetect ContentDetector",
            "scene_threshold": self.threshold,
            "scene_count": len(shots),
            "shots": shots,
        }

    @staticmethod
    def _serialize_scenes(scenes: list[Any]) -> list[dict[str, Any]]:
        shots: list[dict[str, Any]] = []
        for start, end in scenes:
            start_seconds = round(float(start.get_seconds()), 2)
            end_seconds = round(float(end.get_seconds()), 2)
            if end_seconds <= start_seconds:
                continue
            shots.append(
                {
                    "index": len(shots) + 1,
                    "start_seconds": start_seconds,
                    "end_seconds": end_seconds,
                    "duration_seconds": round(end_seconds - start_seconds, 2),
                    "cut_score": None,
                }
            )
        return shots
