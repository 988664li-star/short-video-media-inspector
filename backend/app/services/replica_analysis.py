"""Post-shot services: package scenes, analyze scenes, and build a replica plan."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Awaitable, Callable

from backend.app.core.config import Settings
from backend.app.services.siliconflow import SiliconFlowClient, SiliconFlowError
from backend.app.services.transcription import TranscriptionService


ANALYSIS_ID_PATTERN = re.compile(r"[a-f0-9]{64}")


class ReplicaAnalysisError(RuntimeError):
    """Base error returned by the post-shot replica-analysis APIs."""


class ReplicaAnalysisNotReadyError(ReplicaAnalysisError):
    """A required result from an earlier stage is absent."""


class ReplicaAnalysisModelError(ReplicaAnalysisError):
    """A visual-model request cannot be completed."""


@dataclass(frozen=True)
class ScenePackageConfig:
    data_path: Path
    primary_overlap_seconds: float


ProgressCallback = Callable[[str, str], Awaitable[None]]
SceneCompletedCallback = Callable[[dict[str, Any], int, int], Awaitable[None]]


def _job_path(data_path: Path, analysis_id: str) -> Path:
    if not ANALYSIS_ID_PATTERN.fullmatch(analysis_id):
        raise ReplicaAnalysisNotReadyError("分镜任务标识无效")
    root = data_path.resolve()
    job_path = (root / analysis_id).resolve()
    try:
        job_path.relative_to(root)
    except ValueError as exc:
        raise ReplicaAnalysisNotReadyError("分镜任务路径无效") from exc
    if not (job_path / "scenes.json").is_file():
        raise ReplicaAnalysisNotReadyError("请先完成自动分镜")
    return job_path


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary_path = path.with_suffix(".partial")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_path.replace(path)


class ScenePackageService:
    """Combine saved shots with local F2-style timestamped transcription."""

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
            job_path = _job_path(self.config.data_path, analysis_id)
            package_path = job_path / "scene_packages.json"
            cached = _read_json(package_path)
            if cached is not None:
                if on_progress:
                    await on_progress("packages", "已读取已保存的口播与镜头包")
                return {**cached, "cached": True}

            scenes = _read_json(job_path / "scenes.json")
            source_path = job_path / "source.mp4"
            if scenes is None or not source_path.is_file():
                raise ReplicaAnalysisNotReadyError("自动分镜素材不完整，请重新识别")

            if on_progress:
                await on_progress("transcription", "正在从已下载视频生成带时间戳的口播")
            transcript = await self.transcription_service.transcribe_local_file(
                str(scenes.get("aweme_id", "")), source_path, context
            )
            await asyncio.to_thread(_write_json, job_path / "transcript.json", transcript)
            if on_progress:
                await on_progress("packages", "正在将口播、关键帧和镜头按时间合并")
            packages = self._build_packages(analysis_id, scenes, transcript)
            await asyncio.to_thread(_write_json, package_path, packages)
            return {**packages, "cached": False}

    def load(self, analysis_id: str) -> dict[str, Any]:
        job_path = _job_path(self.config.data_path, analysis_id)
        payload = _read_json(job_path / "scene_packages.json")
        if payload is None:
            raise ReplicaAnalysisNotReadyError("请先生成镜头视觉分析")
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
            segments = self._overlapping_segments(
                transcript_segments, start_ms, end_ms
            )
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
                    "role": "primary"
                    if overlap_ms >= overlap_threshold
                    else "context",
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
                normalized.append(
                    {"start_ms": start_ms, "end_ms": end_ms, "text": text}
                )
        return normalized


class SceneVisualAnalysisService:
    """Call the visual model once for each persisted scene package."""

    _required_fields = (
        "scene_id",
        "scene_type",
        "visual_subject",
        "action",
        "shot_size",
        "camera_angle",
        "camera_motion",
        "scene_description",
        "conversion_purpose",
        "evidence",
    )
    _system_prompt = (
        "你是短视频分镜分析师。只根据所给关键帧和口播分析单个镜头。"
        "camera_motion 只描述相机运动，不要把手部、商品或其他主体的动作当作运镜。"
        "若按时间顺序的关键帧中背景和构图位置稳定，没有全局位移、缩放或摇移证据，"
        "camera_motion 填“静态”。只有关键帧太少、背景不可见或证据互相矛盾时，才填“未知”。"
        "不要虚构看不见的内容。"
        "必须只返回一个 JSON 对象，不要 Markdown。"
    )

    def __init__(self, data_path: Path, client: SiliconFlowClient) -> None:
        self.data_path = data_path
        self.client = client
        self._job_lock = asyncio.Lock()

    async def analyze(
        self,
        analysis_id: str,
        packages: dict[str, Any],
        on_scene_completed: SceneCompletedCallback | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        async with self._job_lock:
            job_path = _job_path(self.data_path, analysis_id)
            output_path = job_path / "scene_analysis.json"
            existing = None if force else _read_json(output_path)
            completed = {
                int(item["scene_id"])
                for item in (existing or {}).get("scene_analyses", [])
                if isinstance(item, dict) and str(item.get("scene_id", "")).isdigit()
            }
            result = existing or {
                "analysis_id": analysis_id,
                "source_scene_packages": "scene_packages.json",
                "model": self.client.config.model,
                "scene_analyses": [],
            }
            pending = [
                scene
                for scene in packages.get("scene_packages", [])
                if isinstance(scene, dict)
                and int(scene.get("scene_id", 0)) not in completed
            ]
            if not pending:
                if on_scene_completed:
                    analyses = result.get("scene_analyses", [])
                    total = len(analyses)
                    for index, analysis in enumerate(analyses, start=1):
                        if isinstance(analysis, dict):
                            await on_scene_completed(analysis, index, total)
                return {**result, "cached": True}

            total = len(packages.get("scene_packages", []))
            for scene in pending:
                try:
                    analysis, usage = await self._analyze_scene(job_path, scene)
                except SiliconFlowError as exc:
                    raise ReplicaAnalysisModelError(str(exc)) from exc
                saved_analysis = {**analysis, "usage": usage}
                result["scene_analyses"].append(saved_analysis)
                await asyncio.to_thread(_write_json, output_path, result)
                if on_scene_completed:
                    await on_scene_completed(
                        saved_analysis,
                        len(result["scene_analyses"]),
                        total,
                    )
            return {**result, "cached": False}

    def load(self, analysis_id: str) -> dict[str, Any]:
        job_path = _job_path(self.data_path, analysis_id)
        payload = _read_json(job_path / "scene_analysis.json")
        if payload is None:
            raise ReplicaAnalysisNotReadyError("请先完成镜头视觉分析")
        return payload

    async def _analyze_scene(
        self, job_path: Path, scene: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        content = await asyncio.to_thread(self._build_scene_message, job_path, scene)
        analysis, usage = await self.client.complete_json(
            system_prompt=self._system_prompt,
            content=content,
            max_tokens=1000,
            timeout_seconds=120,
            temperature=0.1,
        )
        missing = [key for key in self._required_fields if key not in analysis]
        if missing or int(analysis.get("scene_id", -1)) != int(scene["scene_id"]):
            raise ReplicaAnalysisModelError(
                f"视觉模型返回不完整或镜头编号不匹配：{', '.join(missing)}"
            )
        return analysis, usage

    @staticmethod
    def _build_scene_message(job_path: Path, scene: dict[str, Any]) -> list[dict[str, Any]]:
        instructions = {
            "scene_id": scene["scene_id"],
            "time_range_ms": [scene["start_ms"], scene["end_ms"]],
            "primary_transcript": "；".join(scene["primary_transcript"]) or "无",
            "context_transcript": "；".join(scene["context_transcript"]) or "无",
            "required_json": {
                "scene_id": "整数，必须与输入一致",
                "scene_type": "Hook / Proof / Demonstration / CTA / Transition / Other",
                "visual_subject": ["画面主体"],
                "action": "主体动作；不确定填未知",
                "shot_size": "特写 / 近景 / 中景 / 全景 / 未知",
                "camera_angle": "平视 / 俯视 / 仰视 / 顶视 / 未知",
                "camera_motion": "静态 / 推进 / 拉远 / 平移 / 跟拍 / 未知",
                "scene_description": "客观画面描述",
                "conversion_purpose": "该镜头承担的转化作用；不明确填未知",
                "evidence": ["可验证证据"],
            },
        }
        content: list[dict[str, Any]] = [
            {"type": "text", "text": json.dumps(instructions, ensure_ascii=False)}
        ]
        for frame in scene.get("frames", []):
            frame_path = (job_path / str(frame["path"])).resolve()
            try:
                frame_path.relative_to(job_path)
            except ValueError as exc:
                raise ReplicaAnalysisModelError("关键帧路径无效") from exc
            if not frame_path.is_file():
                raise ReplicaAnalysisNotReadyError("关键帧不存在，请重新执行自动分镜")
            image = base64.b64encode(frame_path.read_bytes()).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image}", "detail": "high"},
                }
            )
        return content


class ReplicaPlaybookService:
    """Summarize scene packages and visual analyses into a single replica plan."""

    _system_prompt = (
        "你是爆款短视频的内容策略师和拍摄导演。"
        "依据输入的逐镜头时间、口播、视觉分析，生成可执行的复刻方案。"
        "所有结论必须可追溯到输入；信息不足时明确写“待核对”，不要补造字幕、音效或镜头运动。"
        "复刻的目标是保留内容机制、节奏和视觉证明，不是逐字抄袭。"
        "只返回 JSON 对象，不要 Markdown。"
    )

    def __init__(self, data_path: Path, client: SiliconFlowClient) -> None:
        self.data_path = data_path
        self.client = client
        self._job_lock = asyncio.Lock()

    async def build(
        self,
        analysis_id: str,
        packages: dict[str, Any],
        analyses: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._job_lock:
            job_path = _job_path(self.data_path, analysis_id)
            output_path = job_path / "replica_playbook.json"
            cached = _read_json(output_path)
            if cached is not None:
                return {**cached, "cached": True}

            expected = len(packages.get("scene_packages", []))
            completed = len(analyses.get("scene_analyses", []))
            if expected == 0 or completed < expected:
                raise ReplicaAnalysisNotReadyError("镜头视觉分析尚未完整完成")
            source = {
                "scene_packages": packages["scene_packages"],
                "scene_analyses": analyses["scene_analyses"],
            }
            required_shape = {
                "video_positioning": "一句话定位",
                "content_structure": [
                    {
                        "stage": "Hook / Proof / Demonstration / Product Intro / Usage Detail / CTA / Other",
                        "scene_ids": [1],
                        "time_range_ms": [0, 0],
                        "strategy": "结构策略",
                        "evidence": ["证据"],
                    }
                ],
                "replica_shots": [
                    {
                        "scene_id": 1,
                        "duration_ms": 0,
                        "scene_function": "镜头任务",
                        "shooting_direction": "怎么拍",
                        "voiceover_strategy": "怎么说",
                        "editing_direction": "怎么剪",
                        "must_preserve": ["不可丢失元素"],
                        "adaptable_variables": ["可替换元素"],
                    }
                ],
                "replication_formula": ["内容公式"],
                "production_checklist": ["执行清单"],
                "data_gaps": ["待补信息"],
            }
            content = "输入数据：\n" + json.dumps(
                source, ensure_ascii=False
            ) + "\n\n返回结构：\n" + json.dumps(required_shape, ensure_ascii=False)
            try:
                playbook, usage = await self.client.complete_json(
                    system_prompt=self._system_prompt,
                    content=content,
                    max_tokens=4000,
                    timeout_seconds=180,
                    temperature=0.2,
                )
            except SiliconFlowError as exc:
                raise ReplicaAnalysisModelError(str(exc)) from exc
            result = {
                "analysis_id": analysis_id,
                "source_packages": "scene_packages.json",
                "source_analyses": "scene_analysis.json",
                "model": self.client.config.model,
                "playbook": playbook,
                "usage": usage,
            }
            await asyncio.to_thread(_write_json, output_path, result)
            return {**result, "cached": False}
