"""Local shot splitting and keyframe extraction for canvas video assets."""

from __future__ import annotations

import asyncio
import math
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

import av
from backend.app.services.shot_detection.detector import PySceneDetector
from backend.app.services.shot_detection.errors import ShotDecodeError
from backend.app.services.shot_detection.exporter import SceneAssetExporter

from .generation import MIN_SEEDANCE_VIDEO_SECONDS, PREFERRED_CANVAS_SEGMENT_SECONDS
from .service import CanvasAssetNotFoundError, CanvasProjectService


class CanvasVideoError(RuntimeError):
    """A canvas video cannot be processed into usable derived media."""


class CanvasVideoService:
    """Operate on durable project-local videos and persist derived canvas assets."""

    def __init__(
        self,
        project_service: CanvasProjectService,
        *,
        ffmpeg_binary: str,
        scene_threshold: float,
        min_shot_seconds: float,
        max_asset_bytes: int,
    ) -> None:
        self.project_service = project_service
        self.detector = PySceneDetector(scene_threshold, min_shot_seconds)
        self.exporter = SceneAssetExporter(ffmpeg_binary)
        self.ffmpeg_binary = ffmpeg_binary
        self.max_asset_bytes = max_asset_bytes

    async def split_by_shots(self, project_id: str, asset_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._split_by_shots, project_id, asset_id)

    async def extract_keyframes(self, project_id: str, asset_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._extract_keyframes, project_id, asset_id)

    async def compose_comparison(
        self,
        project_id: str,
        *,
        video_asset_ids: list[str],
        audio_asset_id: str = "",
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._compose_comparison,
            project_id,
            video_asset_ids,
            audio_asset_id,
        )

    async def compose_replacements(
        self,
        project_id: str,
        *,
        shots: list[dict[str, Any]],
        results: list[dict[str, Any]],
        source_audio_asset_id: str = "",
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._compose_replacements,
            project_id,
            shots,
            results,
            source_audio_asset_id,
        )

    def _split_by_shots(self, project_id: str, asset_id: str) -> dict[str, Any]:
        source_asset, source_path = self._source_video(project_id, asset_id)
        duration_seconds = self._video_duration(source_path)
        directory = Path(tempfile.mkdtemp(prefix=f"canvas-video-{asset_id[:8]}-"))
        try:
            generation_shots = self._plan_generation_shots(duration_seconds)
            self.exporter.export(source_path, directory, generation_shots, extract_keyframes=False)
            shots: list[dict[str, Any]] = []
            for shot in generation_shots:
                clip_path = directory / str(shot["clip"])
                clip_asset = self._save_file(
                    project_id,
                    f"{Path(source_asset['filename']).stem}-edit-segment-{int(shot['index']):02d}.mp4",
                    "video/mp4",
                    clip_path,
                )
                shots.append({
                    "index": shot["index"],
                    "start_seconds": shot["start_seconds"],
                    "end_seconds": shot["end_seconds"],
                    "duration_seconds": shot["duration_seconds"],
                    "asset": clip_asset,
                })
            return {
                "source_asset_id": asset_id,
                "duration_seconds": duration_seconds,
                "shots": shots,
            }
        finally:
            self._remove_directory(directory)

    @staticmethod
    def _plan_generation_shots(
        source_duration: float,
    ) -> list[dict[str, Any]]:
        """Create whole-second, contiguous edit spans; scene cuts do not split jobs."""
        if source_duration < MIN_SEEDANCE_VIDEO_SECONDS:
            raise CanvasVideoError(
                f"原视频仅 {source_duration:.2f} 秒，短于 Seedance 最短 {MIN_SEEDANCE_VIDEO_SECONDS:.0f} 秒，不能提交生成"
            )
        windows: list[dict[str, Any]] = []
        start = 0.0
        index = 1
        while source_duration - start > PREFERRED_CANVAS_SEGMENT_SECONDS:
            maximum_end = min(
                start + PREFERRED_CANVAS_SEGMENT_SECONDS,
                source_duration - MIN_SEEDANCE_VIDEO_SECONDS,
            )
            end = float(math.floor(maximum_end))
            duration = end - start
            windows.append({
                "index": index,
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "duration_seconds": round(duration, 3),
            })
            start = end
            index += 1
        remaining = source_duration - start
        if remaining < MIN_SEEDANCE_VIDEO_SECONDS - 0.001:
            raise CanvasVideoError("无法将视频切分为 4–8 秒的连续生成镜头")
        windows.append({
            "index": index,
            "start_seconds": round(start, 3),
            "end_seconds": round(source_duration, 3),
            "duration_seconds": round(remaining, 3),
        })
        return windows

    @staticmethod
    def _video_duration(source_path: Path) -> float:
        try:
            with av.open(str(source_path)) as container:
                stream = container.streams.video[0]
                if stream.duration and stream.time_base:
                    return float(stream.duration * stream.time_base)
                if container.duration:
                    return float(container.duration / av.time_base)
        except (av.error.FFmpegError, IndexError, OSError, ValueError) as exc:
            raise CanvasVideoError(f"无法读取原视频时长：{exc}") from exc
        raise CanvasVideoError("无法读取原视频时长")

    def _extract_keyframes(self, project_id: str, asset_id: str) -> dict[str, Any]:
        source_asset, source_path = self._source_video(project_id, asset_id)
        payload, directory = self._export(source_path, asset_id)
        try:
            frames: list[dict[str, Any]] = []
            for shot in payload["shots"]:
                for frame_index, frame in enumerate(shot.get("selected_frames") or [], start=1):
                    frame_path = directory / str(frame["path"])
                    image_asset = self._save_file(
                        project_id,
                        (
                            f"{Path(source_asset['filename']).stem}-shot-{int(shot['index']):02d}"
                            f"-frame-{frame_index:02d}.jpg"
                        ),
                        "image/jpeg",
                        frame_path,
                    )
                    frames.append({
                        "shot_index": shot["index"],
                        "timestamp_seconds": frame["timestamp_seconds"],
                        "asset": image_asset,
                    })
            return {
                "source_asset_id": asset_id,
                "duration_seconds": payload["duration_seconds"],
                "frames": frames,
            }
        finally:
            self._remove_directory(directory)

    def _compose_replacements(
        self,
        project_id: str,
        shots: list[dict[str, Any]],
        results: list[dict[str, Any]],
        source_audio_asset_id: str,
    ) -> dict[str, Any]:
        if not shots:
            raise CanvasVideoError("没有可合成的镜头")
        result_by_shot = {int(result["shot_index"]): result for result in results}
        clip_paths: list[Path] = []
        for shot in sorted(shots, key=lambda item: int(item["index"])):
            result = result_by_shot.get(int(shot["index"]))
            asset_id = str(result.get("result_asset_id") or "") if result and result.get("status") == "succeeded" else str(shot["asset_id"])
            try:
                _, clip_path = self.project_service.get_asset_file(project_id, asset_id)
            except CanvasAssetNotFoundError as exc:
                raise CanvasVideoError(f"镜头 {int(shot['index']):02d} 的合成素材不存在") from exc
            clip_paths.append(clip_path)
        audio_path: Path | None = None
        if source_audio_asset_id:
            try:
                audio_asset, audio_path = self.project_service.get_asset_file(
                    project_id, source_audio_asset_id
                )
            except CanvasAssetNotFoundError as exc:
                raise CanvasVideoError("连接的音频素材不存在") from exc
            if not str(audio_asset.get("mime_type") or "").startswith(("audio/", "video/")):
                raise CanvasVideoError("连接的素材不是有效音频")
        width, height = self._video_size(clip_paths[0])
        descriptor, output_name = tempfile.mkstemp(
            prefix="canvas-replacement-compose-", suffix=".mp4"
        )
        os.close(descriptor)
        output = Path(output_name)
        try:
            filters = []
            for index, shot in enumerate(sorted(shots, key=lambda item: int(item["index"]))):
                duration = float(shot["duration_seconds"])
                filters.append(
                    f"[{index}:v]trim=duration={duration:.3f},setpts=PTS-STARTPTS,"
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{index}]"
                )
            filters.append(
                "".join(f"[v{index}]" for index in range(len(clip_paths)))
                + f"concat=n={len(clip_paths)}:v=1:a=0[video]"
            )
            command = [self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error"]
            for path in clip_paths:
                command.extend(["-i", str(path)])
            if audio_path is not None:
                command.extend(["-i", str(audio_path)])
            command.extend([
                "-filter_complex", ";".join(filters),
                "-map", "[video]",
            ])
            if audio_path is not None:
                command.extend([
                    "-map", f"{len(clip_paths)}:a:0",
                    "-c:a", "aac",
                    "-af", "apad",
                    "-shortest",
                ])
            else:
                command.append("-an")
            command.extend([
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(output),
            ])
            subprocess.run(command, check=True, capture_output=True, text=True)
            asset = self._save_file(
                project_id,
                "逐镜头替换合成成片.mp4",
                "video/mp4",
                output,
            )
            return {"asset": asset, "used_original_shot_indices": [
                int(shot["index"])
                for shot in shots
                if result_by_shot.get(int(shot["index"]), {}).get("status") != "succeeded"
            ]}
        except FileNotFoundError as exc:
            raise CanvasVideoError("未安装 FFmpeg，无法合成替换成片") from exc
        except subprocess.CalledProcessError as exc:
            raise CanvasVideoError(f"替换成片合成失败：{exc.stderr.strip() or '未知错误'}") from exc
        finally:
            output.unlink(missing_ok=True)

    def _compose_comparison(
        self,
        project_id: str,
        video_asset_ids: list[str],
        audio_asset_id: str,
    ) -> dict[str, Any]:
        if not 2 <= len(video_asset_ids) <= 3:
            raise CanvasVideoError("对比视频需要连接 2～3 个视频素材")
        if len(set(video_asset_ids)) != len(video_asset_ids):
            raise CanvasVideoError("对比视频不能重复使用同一个视频素材")

        video_paths: list[Path] = []
        for asset_id in video_asset_ids:
            _, source_path = self._source_video(project_id, asset_id)
            video_paths.append(source_path)

        explicit_audio_path: Path | None = None
        used_audio_asset_id = ""
        if audio_asset_id:
            try:
                audio_asset, explicit_audio_path = self.project_service.get_asset_file(
                    project_id, audio_asset_id
                )
            except CanvasAssetNotFoundError as exc:
                raise CanvasVideoError("连接的对比视频音频素材不存在") from exc
            if not str(audio_asset.get("mime_type") or "").startswith(("audio/", "video/")):
                raise CanvasVideoError("连接的素材不能作为对比视频音频")
            if not self._has_audio_stream(explicit_audio_path):
                raise CanvasVideoError("连接的音频素材没有可用音轨")
            used_audio_asset_id = audio_asset_id
        else:
            for asset_id, path in zip(video_asset_ids, video_paths, strict=True):
                if self._has_audio_stream(path):
                    used_audio_asset_id = asset_id
                    break

        panel_width, panel_height = self._comparison_panel_size(
            video_paths[0], len(video_paths)
        )
        filters = [
            (
                f"[{index}:v]fps=30,setpts=PTS-STARTPTS,"
                f"scale={panel_width}:{panel_height}:force_original_aspect_ratio=decrease,"
                f"pad={panel_width}:{panel_height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1[v{index}]"
            )
            for index in range(len(video_paths))
        ]
        filters.append(
            "".join(f"[v{index}]" for index in range(len(video_paths)))
            + f"hstack=inputs={len(video_paths)}:shortest=1[video]"
        )

        descriptor, output_name = tempfile.mkstemp(
            prefix="canvas-video-comparison-", suffix=".mp4"
        )
        os.close(descriptor)
        output = Path(output_name)
        try:
            command = [self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error"]
            for path in video_paths:
                command.extend(["-i", str(path)])
            audio_input_index: int | None = None
            if explicit_audio_path is not None:
                audio_input_index = len(video_paths)
                command.extend(["-i", str(explicit_audio_path)])
            elif used_audio_asset_id:
                audio_input_index = video_asset_ids.index(used_audio_asset_id)

            command.extend(["-filter_complex", ";".join(filters), "-map", "[video]"])
            if audio_input_index is None:
                command.append("-an")
            else:
                command.extend([
                    "-map", f"{audio_input_index}:a:0",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-af", "aresample=async=1:first_pts=0,apad",
                    "-shortest",
                ])
            command.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "22",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(output),
            ])
            subprocess.run(command, check=True, capture_output=True, text=True)
            asset = self._save_file(
                project_id,
                f"{len(video_paths)}路同步对比视频.mp4",
                "video/mp4",
                output,
            )
            return {
                "asset": asset,
                "input_count": len(video_paths),
                "audio_source_asset_id": used_audio_asset_id,
            }
        except FileNotFoundError as exc:
            raise CanvasVideoError("未安装 FFmpeg，无法生成对比视频") from exc
        except subprocess.CalledProcessError as exc:
            raise CanvasVideoError(f"对比视频合成失败：{exc.stderr.strip() or '未知错误'}") from exc
        finally:
            output.unlink(missing_ok=True)

    def _comparison_panel_size(self, path: Path, input_count: int) -> tuple[int, int]:
        source_width, source_height = self._video_size(path)
        maximum_panel_width = 1920 / input_count
        scale = min(maximum_panel_width / source_width, 1080 / source_height, 1.0)
        panel_width = max(2, int(source_width * scale) // 2 * 2)
        panel_height = max(2, int(source_height * scale) // 2 * 2)
        return panel_width, panel_height

    @staticmethod
    def _has_audio_stream(path: Path) -> bool:
        try:
            with av.open(str(path)) as container:
                return any(stream.type == "audio" for stream in container.streams)
        except (av.FFmpegError, OSError):
            return False

    def _source_video(self, project_id: str, asset_id: str) -> tuple[dict[str, Any], Path]:
        try:
            asset, source_path = self.project_service.get_asset_file(project_id, asset_id)
        except CanvasAssetNotFoundError as exc:
            raise CanvasVideoError("视频素材不存在，请重新上传") from exc
        if not str(asset.get("mime_type") or "").startswith("video/"):
            raise CanvasVideoError("当前节点没有可处理的视频素材")
        return asset, source_path

    @staticmethod
    def _video_size(path: Path) -> tuple[int, int]:
        try:
            with av.open(str(path)) as container:
                stream = next(stream for stream in container.streams if stream.type == "video")
                if stream.width and stream.height:
                    return stream.width, stream.height
        except (av.FFmpegError, StopIteration) as exc:
            raise CanvasVideoError("无法读取合成镜头尺寸") from exc
        raise CanvasVideoError("无法读取合成镜头尺寸")

    def _export(
        self,
        source_path: Path,
        asset_id: str,
        *,
        export_detected_shots: bool = True,
    ) -> tuple[dict[str, Any], Path]:
        directory = Path(tempfile.mkdtemp(prefix=f"canvas-video-{asset_id[:8]}-"))
        try:
            payload = self.detector.detect(asset_id, source_path)
            if not payload["shots"]:
                raise CanvasVideoError("没有识别到可用镜头")
            if export_detected_shots:
                self.exporter.export(source_path, directory, payload["shots"])
            return payload, directory
        except ShotDecodeError as exc:
            self._remove_directory(directory)
            raise CanvasVideoError(str(exc)) from exc
        except Exception as exc:
            self._remove_directory(directory)
            raise CanvasVideoError(f"视频处理失败：{exc}") from exc

    def _save_file(
        self,
        project_id: str,
        filename: str,
        mime_type: str,
        path: Path,
    ) -> dict[str, Any]:
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise CanvasVideoError("视频处理结果文件不存在") from exc
        if len(content) > self.max_asset_bytes:
            raise CanvasVideoError("处理结果超过画布素材大小限制")
        return self.project_service.save_asset(project_id, filename, mime_type, content)

    @staticmethod
    def _remove_directory(directory: Path) -> None:
        import shutil

        shutil.rmtree(directory, ignore_errors=True)
