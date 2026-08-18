from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any

import aiofiles
import httpx

from backend.app.core.config import Settings
from backend.app.services.media import MediaResource


class ShotDetectionError(RuntimeError):
    """Base error exposed by the automatic shot-detection API."""


class ShotMediaDownloadError(ShotDetectionError):
    """The allowlisted source video could not be downloaded."""


class ShotDecodeError(ShotDetectionError):
    """The downloaded video cannot be decoded into frames."""


@dataclass(frozen=True)
class ShotDetectionConfig:
    data_path: Path
    max_media_bytes: int
    scene_threshold: float
    min_shot_seconds: float
    cache_ttl_seconds: int
    ffmpeg_binary: str


class ShotDetectionService:
    """Persist one source video and detect its shot boundaries with PySceneDetect."""

    def __init__(self, config: ShotDetectionConfig) -> None:
        self.config = config
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
            cached = await asyncio.to_thread(self._read_cached_result, cache_key)
            if cached is not None:
                cached["cached"] = True
                return cached

            job_path = self.config.data_path / cache_key
            source_path = job_path / "source.mp4"
            result_path = job_path / "scenes.json"
            try:
                await asyncio.to_thread(job_path.mkdir, parents=True, exist_ok=True, mode=0o700)
                await self._download_video(resource, source_path)
                started_at = time.perf_counter()
                payload = await asyncio.to_thread(
                    self._detect_file,
                    aweme_id,
                    source_path,
                    job_path,
                )
                payload["analysis_id"] = cache_key
                payload["elapsed_seconds"] = round(time.perf_counter() - started_at, 2)
                payload["cached"] = False
                await asyncio.to_thread(self._write_result, result_path, payload)
                return payload
            except Exception:
                await asyncio.to_thread(self._remove_incomplete_job, job_path, result_path)
                raise

    async def _download_video(self, resource: MediaResource, destination: Path) -> None:
        temporary_path = destination.with_suffix(".partial")
        timeout = httpx.Timeout(connect=20, read=120, write=30, pool=20)
        downloaded = 0
        try:
            async with httpx.AsyncClient(
                headers=resource.headers,
                follow_redirects=True,
                timeout=timeout,
            ) as client:
                async with client.stream("GET", resource.source_url) as response:
                    response.raise_for_status()
                    content_length = int(response.headers.get("Content-Length", "0"))
                    if content_length > self.config.max_media_bytes:
                        raise ShotMediaDownloadError("视频文件过大，暂不支持自动分镜")

                    async with aiofiles.open(temporary_path, "wb") as output:
                        async for chunk in response.aiter_bytes(256 * 1024):
                            downloaded += len(chunk)
                            if downloaded > self.config.max_media_bytes:
                                raise ShotMediaDownloadError(
                                    "视频文件过大，暂不支持自动分镜"
                                )
                            await output.write(chunk)
            if downloaded == 0:
                raise ShotMediaDownloadError("视频文件为空，无法进行分镜识别")
            await asyncio.to_thread(temporary_path.replace, destination)
        except ShotMediaDownloadError:
            raise
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise ShotMediaDownloadError(f"视频下载失败：{exc}") from exc
        finally:
            if temporary_path.exists():
                await asyncio.to_thread(temporary_path.unlink)

    def _detect_file(
        self,
        aweme_id: str,
        source_path: Path,
        job_path: Path | None = None,
    ) -> dict[str, Any]:
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
        min_scene_len = max(1, round(frame_rate * self.config.min_shot_seconds))
        scene_manager.add_detector(
            ContentDetector(
                threshold=self.config.scene_threshold,
                min_scene_len=min_scene_len,
            )
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
        if job_path is not None:
            self._export_scene_assets(source_path, job_path, shots)
        return {
            "aweme_id": aweme_id,
            "duration_seconds": round(duration, 2),
            "fps": frame_rate,
            "detector": "PySceneDetect ContentDetector",
            "scene_threshold": self.config.scene_threshold,
            "scene_count": len(shots),
            "shots": shots,
        }

    def _export_scene_assets(
        self,
        source_path: Path,
        job_path: Path,
        shots: list[dict[str, Any]],
    ) -> None:
        for shot in shots:
            scene_dir = job_path / f"scene_{int(shot['index']):03d}"
            scene_dir.mkdir(exist_ok=True, mode=0o700)
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
                "-ss",
                f"{start_seconds:.3f}",
                "-i",
                str(source_path),
                "-t",
                f"{duration_seconds:.3f}",
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

    def _select_keyframes(
        self,
        source_path: Path,
        scene_dir: Path,
        start_seconds: float,
        duration_seconds: float,
    ) -> dict[str, Any]:
        candidate_dir = scene_dir / "candidates"
        selected_dir = scene_dir / "selected"
        candidate_dir.mkdir(exist_ok=True, mode=0o700)
        selected_dir.mkdir(exist_ok=True, mode=0o700)
        candidate_positions = (0.2, 0.5, 0.8)
        candidate_data: list[dict[str, Any]] = []
        signatures: list[Any] = []
        for position in candidate_positions:
            timestamp = start_seconds + duration_seconds * position
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
            timestamp = start_seconds + duration_seconds * position
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
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(source_path),
                "-frames:v",
                "1",
                "-q:v",
                str(quality),
                str(output_path),
            ]
        )

    def _run_ffmpeg(self, arguments: list[str]) -> None:
        command = [
            self.config.ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            *arguments,
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

    def _cache_key(self, aweme_id: str, source_url: str) -> str:
        value = "|".join(
            (
                aweme_id,
                source_url,
                "pyscenedetect-content-v1",
                str(self.config.scene_threshold),
                str(self.config.min_shot_seconds),
            )
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _read_cached_result(self, cache_key: str) -> dict[str, Any] | None:
        result_path = self.config.data_path / cache_key / "scenes.json"
        source_path = result_path.with_name("source.mp4")
        try:
            if self._is_expired(result_path) or not source_path.is_file():
                return None
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) and isinstance(payload.get("shots"), list) else None
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_result(result_path: Path, payload: dict[str, Any]) -> None:
        temporary_path = result_path.with_suffix(".partial")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(result_path)

    def cleanup_expired_cache(self) -> int:
        try:
            jobs = list(self.config.data_path.iterdir())
        except OSError:
            return 0

        removed = 0
        for job_path in jobs:
            if not job_path.is_dir():
                continue
            result_path = job_path / "scenes.json"
            try:
                if self._is_expired(result_path):
                    shutil.rmtree(job_path)
                    removed += 1
            except OSError:
                continue
        return removed

    def get_scene_asset(self, analysis_id: str, relative_path: str) -> Path | None:
        if not re.fullmatch(r"[a-f0-9]{64}", analysis_id):
            return None
        job_path = (self.config.data_path / analysis_id).resolve()
        candidate_path = (job_path / relative_path).resolve()
        try:
            relative_to_job = candidate_path.relative_to(job_path)
        except ValueError:
            return None
        if not relative_to_job.parts or not relative_to_job.parts[0].startswith("scene_"):
            return None
        return candidate_path if candidate_path.is_file() else None

    def _is_expired(self, result_path: Path) -> bool:
        if self.config.cache_ttl_seconds <= 0:
            return False
        try:
            return time.time() - result_path.stat().st_mtime > self.config.cache_ttl_seconds
        except OSError:
            return True

    @staticmethod
    def _remove_incomplete_job(job_path: Path, result_path: Path) -> None:
        if result_path.exists():
            return
        try:
            shutil.rmtree(job_path)
        except OSError:
            pass
