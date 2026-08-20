"""Build timestamp-aligned scene packages from saved shots and transcription."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from backend.app.core.config import Settings
from backend.app.services.replica_analysis.common import (
    ReplicaAnalysisNotReadyError,
    job_path,
    read_json,
    write_json,
)
from backend.app.services.transcription import TranscriptionService


ProgressCallback = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True)
class ScenePackageConfig:
    data_path: Path
    primary_overlap_seconds: float


class ScenePackageService:
    """Combine saved shots with local F2-style timestamped transcription."""

    _package_version = 3

    def __init__(
        self,
        config: ScenePackageConfig,
        transcription_service: TranscriptionService,
    ) -> None:
        self.config = config
        self.transcription_service = transcription_service
        self._job_lock = asyncio.Lock()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        transcription_service: TranscriptionService,
    ) -> "ScenePackageService":
        return cls(
            ScenePackageConfig(
                data_path=settings.shot_detection_data_path,
                primary_overlap_seconds=settings.replica_primary_overlap_seconds,
            ),
            transcription_service,
        )

    async def create(
        self,
        analysis_id: str,
        context: str = "",
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        async with self._job_lock:
            target = job_path(self.config.data_path, analysis_id)
            package_path = target / "scene_packages.json"
            cached = read_json(package_path)
            if cached is not None and cached.get("package_version") == self._package_version:
                if on_progress:
                    await on_progress("packages", "已读取已保存的口播与镜头包")
                return {**cached, "cached": True}

            scenes = read_json(target / "scenes.json")
            source_path = target / "source.mp4"
            if scenes is None or not source_path.is_file():
                raise ReplicaAnalysisNotReadyError("自动分镜素材不完整，请重新识别")
            if on_progress:
                await on_progress("transcription", "正在从已下载视频生成带时间戳的口播")
            transcript = await self.transcription_service.transcribe_local_file(
                str(scenes.get("aweme_id", "")),
                source_path,
                context,
                target / "audio" / "vocals.mp3",
            )
            await asyncio.to_thread(write_json, target / "transcript.json", transcript)
            if on_progress:
                await on_progress("packages", "正在将口播、关键帧和镜头按时间合并")
            packages = self._build_packages(analysis_id, scenes, transcript)
            await asyncio.to_thread(write_json, package_path, packages)
            return {**packages, "cached": False}

    def load(self, analysis_id: str) -> dict[str, Any]:
        target = job_path(self.config.data_path, analysis_id)
        payload = read_json(target / "scene_packages.json")
        if payload is None:
            raise ReplicaAnalysisNotReadyError("请先生成分段分镜脚本")
        return payload

    def _build_packages(
        self,
        analysis_id: str,
        scenes: dict[str, Any],
        transcript: dict[str, Any],
    ) -> dict[str, Any]:
        transcript_segments = self._normalize_segments(transcript)
        packages: list[dict[str, Any]] = []
        for shot in scenes.get("shots", []):
            if not isinstance(shot, dict):
                continue
            start_seconds = float(shot.get("start_seconds", 0))
            end_seconds = float(shot.get("end_seconds", 0))
            if end_seconds <= start_seconds:
                continue
            start_ms = round(start_seconds * 1000)
            end_ms = round(end_seconds * 1000)
            segments = self._overlapping_segments(transcript_segments, start_ms, end_ms)
            frames = [
                {
                    "path": str(frame["path"]),
                    "timestamp_ms": round(float(frame["timestamp_seconds"]) * 1000),
                }
                for frame in shot.get("selected_frames", [])
                if isinstance(frame, dict)
                and isinstance(frame.get("path"), str)
                and frame.get("timestamp_seconds") is not None
            ]
            packages.append(
                {
                    "scene_id": int(shot.get("index", len(packages) + 1)),
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "frames": frames,
                    "transcript_segments": segments,
                    "primary_transcript": [
                        item["text"] for item in segments if item["role"] == "primary"
                    ],
                    "context_transcript": [
                        item["text"] for item in segments if item["role"] == "context"
                    ],
                }
            )
        return {
            "analysis_id": analysis_id,
            "package_version": self._package_version,
            "source_scenes": "scenes.json",
            "source_transcript": "transcript.json",
            "scene_count": len(packages),
            "primary_overlap_ms": round(self.config.primary_overlap_seconds * 1000),
            "scene_packages": packages,
        }

    def _overlapping_segments(
        self,
        transcript_segments: list[dict[str, Any]],
        start_ms: int,
        end_ms: int,
    ) -> list[dict[str, Any]]:
        overlap_threshold = round(self.config.primary_overlap_seconds * 1000)
        segments: list[dict[str, Any]] = []
        for segment in transcript_segments:
            overlap_start = max(start_ms, segment["start_ms"])
            overlap_end = min(end_ms, segment["end_ms"])
            overlap_ms = overlap_end - overlap_start
            if overlap_ms <= 0:
                continue
            segments.append(
                {
                    **segment,
                    "overlap_start_ms": overlap_start,
                    "overlap_end_ms": overlap_end,
                    "overlap_ms": overlap_ms,
                    "role": "primary" if overlap_ms >= overlap_threshold else "context",
                }
            )
        return segments

    @staticmethod
    def _normalize_segments(transcript: dict[str, Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for segment in transcript.get("segments", []):
            if not isinstance(segment, dict):
                continue
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            start_seconds = segment.get("start", segment.get("start_seconds"))
            end_seconds = segment.get("end", segment.get("end_seconds"))
            if start_seconds is None or end_seconds is None:
                continue
            start_ms = round(float(start_seconds) * 1000)
            end_ms = round(float(end_seconds) * 1000)
            if end_ms > start_ms:
                normalized.append({"start_ms": start_ms, "end_ms": end_ms, "text": text})
        return normalized
