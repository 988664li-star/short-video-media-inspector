"""Local shot splitting and keyframe extraction for canvas video assets."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
from typing import Any

from backend.app.services.shot_detection.detector import PySceneDetector
from backend.app.services.shot_detection.errors import ShotDecodeError
from backend.app.services.shot_detection.exporter import SceneAssetExporter

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
        self.max_asset_bytes = max_asset_bytes

    async def split_by_shots(self, project_id: str, asset_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._split_by_shots, project_id, asset_id)

    async def extract_keyframes(self, project_id: str, asset_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._extract_keyframes, project_id, asset_id)

    def _split_by_shots(self, project_id: str, asset_id: str) -> dict[str, Any]:
        source_asset, source_path = self._source_video(project_id, asset_id)
        payload, directory = self._export(source_path, asset_id)
        try:
            shots: list[dict[str, Any]] = []
            for shot in payload["shots"]:
                clip_path = directory / str(shot["clip"])
                clip_asset = self._save_file(
                    project_id,
                    f"{Path(source_asset['filename']).stem}-shot-{int(shot['index']):02d}.mp4",
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
                "duration_seconds": payload["duration_seconds"],
                "shots": shots,
            }
        finally:
            self._remove_directory(directory)

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

    def _source_video(self, project_id: str, asset_id: str) -> tuple[dict[str, Any], Path]:
        try:
            asset, source_path = self.project_service.get_asset_file(project_id, asset_id)
        except CanvasAssetNotFoundError as exc:
            raise CanvasVideoError("视频素材不存在，请重新上传") from exc
        if not str(asset.get("mime_type") or "").startswith("video/"):
            raise CanvasVideoError("当前节点没有可处理的视频素材")
        return asset, source_path

    def _export(self, source_path: Path, asset_id: str) -> tuple[dict[str, Any], Path]:
        directory = Path(tempfile.mkdtemp(prefix=f"canvas-video-{asset_id[:8]}-"))
        try:
            payload = self.detector.detect(asset_id, source_path)
            if not payload["shots"]:
                raise CanvasVideoError("没有识别到可用镜头")
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
