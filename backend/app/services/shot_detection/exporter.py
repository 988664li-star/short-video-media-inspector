"""Export scene clips and select representative keyframes for each scene."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from backend.app.services.shot_detection.errors import ShotDecodeError


class SceneAssetExporter:
    """Write one scene clip plus visual-change-aware keyframes per detected shot."""

    def __init__(self, ffmpeg_binary: str) -> None:
        self.ffmpeg_binary = ffmpeg_binary

    def export(
        self,
        source_path: Path,
        job_path: Path,
        shots: list[dict[str, Any]],
    ) -> None:
        source_duration = self._source_duration(source_path)
        for shot in shots:
            scene_dir = job_path / f"scene_{int(shot['index']):03d}"
            scene_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            clip_path = scene_dir / "video.mp4"
            self._export_scene_clip(
                source_path,
                clip_path,
                float(shot["start_seconds"]),
                float(shot["duration_seconds"]),
            )
            shot["clip"] = clip_path.relative_to(job_path).as_posix()
            frame_data = self._select_keyframes(
                source_path,
                scene_dir,
                float(shot["start_seconds"]),
                float(shot["duration_seconds"]),
                source_duration,
            )
            scene_prefix = scene_dir.relative_to(job_path).as_posix()
            for key in ("candidate_frame_data", "selected_frames"):
                for frame in frame_data[key]:
                    frame["path"] = f"{scene_prefix}/{frame['path']}"
            shot.update(frame_data)

    def _export_scene_clip(
        self,
        source_path: Path,
        output_path: Path,
        start_seconds: float,
        duration_seconds: float,
    ) -> None:
        self._run_ffmpeg(
            [
                "-ss", f"{start_seconds:.3f}", "-i", str(source_path),
                "-t", f"{duration_seconds:.3f}", "-map", "0:v:0", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-movflags", "+faststart", str(output_path),
            ]
        )

    def _select_keyframes(
        self,
        source_path: Path,
        scene_dir: Path,
        start_seconds: float,
        duration_seconds: float,
        source_duration: float,
    ) -> dict[str, Any]:
        candidate_dir = scene_dir / "candidates"
        selected_dir = scene_dir / "selected"
        candidate_dir.mkdir(exist_ok=True, mode=0o700)
        selected_dir.mkdir(exist_ok=True, mode=0o700)
        candidate_positions = (0.2, 0.5, 0.8)
        candidate_data: list[dict[str, Any]] = []
        signatures: list[Any] = []
        for position in candidate_positions:
            timestamp = self._frame_timestamp(
                start_seconds, duration_seconds, position, source_duration
            )
            filename = f"candidate_{round(position * 100):02d}.jpg"
            output_path = candidate_dir / filename
            self._export_frame(source_path, output_path, timestamp, quality=6)
            signatures.append(self._image_signature(output_path))
            candidate_data.append(
                {
                    "position": position,
                    "timestamp_seconds": round(timestamp, 2),
                    "path": output_path.relative_to(scene_dir).as_posix(),
                }
            )

        import numpy as np

        pair_scores = [
            self._difference(signatures[0], signatures[1], np),
            self._difference(signatures[1], signatures[2], np),
        ]
        visual_change_score = max(pair_scores)
        if duration_seconds <= 0.8 or visual_change_score < 0.12:
            selected_positions = (0.5,)
        elif visual_change_score < 0.35:
            selected_positions = (0.25, 0.75)
        else:
            selected_positions = candidate_positions

        selected_frames: list[dict[str, Any]] = []
        for index, position in enumerate(selected_positions, start=1):
            timestamp = self._frame_timestamp(
                start_seconds, duration_seconds, position, source_duration
            )
            filename = f"frame_{index:02d}_{round(position * 100):02d}.jpg"
            output_path = selected_dir / filename
            self._export_frame(source_path, output_path, timestamp, quality=2)
            selected_frames.append(
                {
                    "position": position,
                    "timestamp_seconds": round(timestamp, 2),
                    "path": output_path.relative_to(scene_dir).as_posix(),
                }
            )
        return {
            "candidate_frame_positions": list(candidate_positions),
            "candidate_frame_data": candidate_data,
            "pair_change_scores": [round(score, 4) for score in pair_scores],
            "visual_change_score": round(visual_change_score, 4),
            "selected_frame_positions": list(selected_positions),
            "selected_frames": selected_frames,
        }

    def _export_frame(
        self,
        source_path: Path,
        output_path: Path,
        timestamp: float,
        quality: int,
    ) -> None:
        self._run_ffmpeg(
            [
                "-ss", f"{timestamp:.3f}", "-i", str(source_path),
                "-frames:v", "1", "-q:v", str(quality), str(output_path),
            ]
        )
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise ShotDecodeError(
                f"FFmpeg 未导出关键帧：{timestamp:.3f} 秒处没有可解码画面"
            )

    @staticmethod
    def _frame_timestamp(
        start_seconds: float,
        duration_seconds: float,
        position: float,
        source_duration: float,
    ) -> float:
        # SceneDetect 对可变帧率视频的尾帧时间可能略超过 FFmpeg 的可解码范围。
        # 导出帧时始终留出一个帧间隔，避免在 EOF 上请求一张不存在的图片。
        requested = max(0.0, start_seconds + duration_seconds * position)
        last_decodable = max(0.0, source_duration - 0.1)
        return min(requested, last_decodable)

    def _source_duration(self, source_path: Path) -> float:
        probe_binary = (
            str(Path(self.ffmpeg_binary).with_name("ffprobe"))
            if "/" in self.ffmpeg_binary
            else "ffprobe"
        )
        try:
            result = subprocess.run(
                [
                    probe_binary,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(source_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            duration = float(result.stdout.strip())
        except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as exc:
            raise ShotDecodeError("无法读取参考视频时长，不能导出关键帧") from exc
        if duration <= 0:
            raise ShotDecodeError("参考视频时长无效，不能导出关键帧")
        return duration

    def _run_ffmpeg(self, arguments: list[str]) -> None:
        command = [
            self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error", *arguments
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise ShotDecodeError("未安装 FFmpeg，无法导出分镜素材") from exc
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or "未知 FFmpeg 错误"
            raise ShotDecodeError(f"导出分镜素材失败：{detail}") from exc

    def _image_signature(self, image_path: Path) -> Any:
        try:
            import av
            import numpy as np

            with av.open(str(image_path)) as container:
                frame = next(container.decode(video=0))
            return self._frame_signature(frame, np)
        except Exception as exc:
            raise ShotDecodeError(f"无法读取关键帧：{exc}") from exc

    @staticmethod
    def _frame_signature(frame: Any, np: Any) -> Any:
        preview = frame.reformat(width=64, height=36, format="rgb24")
        pixels = preview.to_ndarray()
        histograms = []
        for channel in range(3):
            values = pixels[:, :, channel].reshape(-1)
            histogram = np.bincount(values // 16, minlength=16).astype("float32")
            histograms.append(histogram / max(1, values.size))
        return np.concatenate(histograms)

    @staticmethod
    def _difference(previous: Any, current: Any, np: Any) -> float:
        return float(np.abs(previous - current).sum() / 6)
