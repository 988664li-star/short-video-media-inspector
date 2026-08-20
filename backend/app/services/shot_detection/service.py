"""Orchestrate automatic shot detection without owning component internals."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import re
import time
from typing import Any

from backend.app.core.config import Settings
from backend.app.services.media import MediaResource
from backend.app.services.shot_detection.config import ShotDetectionConfig
from backend.app.services.shot_detection.detector import PySceneDetector
from backend.app.services.shot_detection.downloader import VideoDownloader
from backend.app.services.shot_detection.errors import ShotDetectionError
from backend.app.services.shot_detection.exporter import SceneAssetExporter
from backend.app.services.shot_detection.store import ShotDetectionStore


logger = logging.getLogger(__name__)


class ShotDetectionService:
    """Persist one source video and coordinate its PySceneDetect workflow."""

    def __init__(self, config: ShotDetectionConfig) -> None:
        self.config = config
        self._downloader = VideoDownloader(config.max_media_bytes)
        self._detector = PySceneDetector(config.scene_threshold, config.min_shot_seconds)
        self._exporter = SceneAssetExporter(config.ffmpeg_binary)
        self._store = ShotDetectionStore(config.data_path, config.cache_ttl_seconds)
        self._job_lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> "ShotDetectionService":
        return cls(
            ShotDetectionConfig(
                data_path=settings.shot_detection_data_path,
                max_media_bytes=settings.shot_detection_max_media_bytes,
                scene_threshold=settings.shot_detection_scene_threshold,
                min_shot_seconds=settings.shot_detection_min_shot_seconds,
                cache_ttl_seconds=settings.shot_detection_cache_ttl_seconds,
                ffmpeg_binary=settings.shot_detection_ffmpeg_binary,
            )
        )

    async def detect(self, aweme_id: str, resource: MediaResource) -> dict[str, Any]:
        if resource.kind != "video":
            raise ShotDetectionError("当前媒体不是视频，无法进行分镜识别")
        cache_key = self._cache_key(aweme_id, resource.source_url)
        async with self._job_lock:
            await asyncio.to_thread(self.cleanup_expired_cache)
            cached = await asyncio.to_thread(self._store.read_result, cache_key)
            if cached is not None:
                cached["cached"] = True
                return cached

            job_path = self.config.data_path / cache_key
            source_path = job_path / "source.mp4"
            result_path = job_path / "scenes.json"
            active_path = job_path / ".active"
            try:
                await asyncio.to_thread(job_path.mkdir, parents=True, exist_ok=True, mode=0o700)
                await asyncio.to_thread(active_path.touch, exist_ok=True)
                if not self._is_ready_source(source_path):
                    await self._download_video(resource, source_path)
                started_at = time.perf_counter()
                payload = await asyncio.to_thread(
                    self._detect_file, aweme_id, source_path, job_path
                )
                payload["analysis_id"] = cache_key
                payload["elapsed_seconds"] = round(time.perf_counter() - started_at, 2)
                payload["cached"] = False
                await asyncio.to_thread(self._store.write_result, result_path, payload)
                return payload
            except Exception as exc:
                logger.exception(
                    "自动分镜失败 [analysis_id=%s, aweme_id=%s]: %s",
                    cache_key,
                    aweme_id,
                    exc,
                )
                # 已落盘的源视频是后续重试和关键帧自愈的基础，不能因为一次
                # 分镜失败就删除它、再依赖可能已经过期的 CDN 地址。
                await asyncio.to_thread(result_path.unlink, missing_ok=True)
                raise
            finally:
                await asyncio.to_thread(active_path.unlink, missing_ok=True)

    async def capture_source(self, aweme_id: str, resource: MediaResource) -> dict[str, Any]:
        """Persist the resolved reference video before the user starts analysis."""
        if resource.kind != "video":
            raise ShotDetectionError("当前媒体不是视频，无法保存为参考视频")
        cache_key = self._cache_key(aweme_id, resource.source_url)
        async with self._job_lock:
            await asyncio.to_thread(self.cleanup_expired_cache)
            job_path = self.config.data_path / cache_key
            source_path = job_path / "source.mp4"
            active_path = job_path / ".active"
            if self._is_ready_source(source_path):
                return {"analysis_id": cache_key, "cached": True}
            try:
                await asyncio.to_thread(job_path.mkdir, parents=True, exist_ok=True, mode=0o700)
                await asyncio.to_thread(active_path.touch, exist_ok=True)
                await self._download_video(resource, source_path)
                return {"analysis_id": cache_key, "cached": False}
            finally:
                await asyncio.to_thread(active_path.unlink, missing_ok=True)

    async def detect_saved_source(self, aweme_id: str, analysis_id: str) -> dict[str, Any]:
        """Run scene detection using a reference video already stored locally."""
        expected_id = self._cache_key(aweme_id, "")
        if analysis_id != expected_id:
            raise ShotDetectionError("本地参考视频与当前作品不匹配，请重新解析")
        async with self._job_lock:
            await asyncio.to_thread(self.cleanup_expired_cache)
            cached = await asyncio.to_thread(self._store.read_result, analysis_id)
            if cached is not None:
                cached["cached"] = True
                return cached
            job_path = self.config.data_path / analysis_id
            source_path = job_path / "source.mp4"
            if not self._is_ready_source(source_path):
                raise ShotDetectionError("本地参考视频不存在或已过期，请重新解析并提取视频")
            active_path = job_path / ".active"
            result_path = job_path / "scenes.json"
            try:
                await asyncio.to_thread(active_path.touch, exist_ok=True)
                started_at = time.perf_counter()
                payload = await asyncio.to_thread(
                    self._detect_file, aweme_id, source_path, job_path
                )
                payload["analysis_id"] = analysis_id
                payload["elapsed_seconds"] = round(time.perf_counter() - started_at, 2)
                payload["cached"] = False
                await asyncio.to_thread(self._store.write_result, result_path, payload)
                return payload
            except Exception as exc:
                logger.exception("本地参考视频自动分镜失败 [analysis_id=%s]: %s", analysis_id, exc)
                await asyncio.to_thread(result_path.unlink, missing_ok=True)
                raise
            finally:
                await asyncio.to_thread(active_path.unlink, missing_ok=True)

    async def _download_video(self, resource: MediaResource, destination: Path) -> None:
        await self._downloader.download(resource, destination)

    def _cache_key(self, aweme_id: str, source_url: str) -> str:
        return self._store.cache_key(
            aweme_id,
            source_url,
            self.config.scene_threshold,
            self.config.min_shot_seconds,
        )

    @staticmethod
    def _is_ready_source(source_path: Path) -> bool:
        try:
            return source_path.is_file() and source_path.stat().st_size > 0
        except OSError:
            return False

    def _detect_file(
        self,
        aweme_id: str,
        source_path: Path,
        job_path: Path | None = None,
    ) -> dict[str, Any]:
        payload = self._detector.detect(aweme_id, source_path)
        if job_path is not None:
            self._exporter.export(source_path, job_path, payload["shots"])
        return payload

    def cleanup_expired_cache(self) -> int:
        return self._store.cleanup_expired()

    def load(self, analysis_id: str) -> dict[str, Any] | None:
        """Load a completed persisted analysis without downloading or detecting again."""
        if not re.fullmatch(r"[a-f0-9]{64}", analysis_id):
            return None
        return self._store.read_result(analysis_id)

    def get_scene_asset(self, analysis_id: str, relative_path: str) -> Path | None:
        return self._store.get_asset(analysis_id, relative_path)
