"""Model orchestration for a single bounded storyboard chunk."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from backend.app.services.replica_analysis.common import (
    ReplicaAnalysisModelError,
    ReplicaAnalysisNotReadyError,
    job_path as resolve_job_path,
    read_json,
    write_json,
)
from backend.app.services.siliconflow import SiliconFlowClient, SiliconFlowError
from backend.app.services.storyboard.prompts import StoryboardPromptTemplate


StoryboardCompletedCallback = Callable[[dict[str, Any], int, int], Awaitable[None]]


class StoryboardScriptService:
    """Turn bounded contact sheets and transcripts into segment scripts."""

    _required_fields = ("segment_id", "segment_summary", "storyboard", "segment_script")
    _required_shot_text_fields = (
        "title",
        "scene_type",
        "visual_description",
        "action",
        "shot_size",
        "camera_angle",
        "camera_motion",
        "shooting_notes",
    )
    _generator_version = 4

    def __init__(
        self,
        data_path: Path,
        client: SiliconFlowClient,
        prompt_template: StoryboardPromptTemplate | None = None,
    ) -> None:
        self.data_path = data_path
        self.client = client
        self.prompt_template = prompt_template
        self._job_lock = asyncio.Lock()

    async def build(
        self,
        analysis_id: str,
        manifest: dict[str, Any],
        context: str = "",
        on_segment_completed: StoryboardCompletedCallback | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        async with self._job_lock:
            target = resolve_job_path(self.data_path, analysis_id)
            prompt_template = self.prompt_template or StoryboardPromptTemplate.load()
            output_path = target / "storyboard_chunks" / "scripts.json"
            cached = None if force else read_json(output_path)
            existing = (
                cached
                if cached and cached.get("generator_version") == self._generator_version
                else None
            )
            completed = {
                int(item["segment_id"])
                for item in (existing or {}).get("segments", [])
                if isinstance(item, dict) and str(item.get("segment_id", "")).isdigit()
            }
            result = existing or {
                "analysis_id": analysis_id,
                "source_manifest": "storyboard_chunks/manifest.json",
                "generator_version": self._generator_version,
                "model": self.client.config.model,
                "segments": [],
            }
            chunks = [chunk for chunk in manifest.get("chunks", []) if isinstance(chunk, dict)]
            pending = [chunk for chunk in chunks if int(chunk.get("segment_id", 0)) not in completed]
            if not pending:
                if on_segment_completed:
                    for order, segment in enumerate(result["segments"], start=1):
                        await on_segment_completed(segment, order, len(result["segments"]))
                return {**result, "cached": True}

            total = len(chunks)
            for chunk in pending:
                previous_summary = self._previous_summary(result, int(chunk["segment_id"]))
                try:
                    script, usage = await self._write_segment(
                        target,
                        chunk,
                        context,
                        previous_summary,
                        prompt_template,
                    )
                except SiliconFlowError as exc:
                    raise ReplicaAnalysisModelError(str(exc)) from exc
                self._validate_script(script, int(chunk["segment_id"]))
                self._attach_original_dialogue(script, chunk)
                saved_segment = {
                    **script,
                    "start_ms": chunk["start_ms"],
                    "end_ms": chunk["end_ms"],
                    "duration_ms": chunk["duration_ms"],
                    "contact_sheet": chunk["contact_sheet"],
                    "usage": usage,
                }
                result["segments"].append(saved_segment)
                result["segments"].sort(key=lambda item: int(item["segment_id"]))
                await asyncio.to_thread(write_json, output_path, result)
                if on_segment_completed:
                    await on_segment_completed(
                        saved_segment, len(result["segments"]), total
                    )
            return {**result, "cached": False}

    def load(self, analysis_id: str) -> dict[str, Any]:
        """Load scripts only after every bounded segment has completed."""
        target = resolve_job_path(self.data_path, analysis_id)
        payload = read_json(target / "storyboard_chunks" / "scripts.json")
        if payload is None:
            raise ReplicaAnalysisNotReadyError("请先完成分段分镜脚本")
        return payload

    @staticmethod
    def _previous_summary(result: dict[str, Any], segment_id: int) -> str:
        previous = [
            item
            for item in result.get("segments", [])
            if isinstance(item, dict) and int(item.get("segment_id", 0)) == segment_id - 1
        ]
        return str(previous[0].get("segment_summary", "")) if previous else "无"

    @classmethod
    def _validate_script(cls, script: dict[str, Any], segment_id: int) -> None:
        missing = [field for field in cls._required_fields if field not in script]
        if missing or int(script.get("segment_id", -1)) != segment_id:
            raise ReplicaAnalysisModelError(
                f"分段脚本返回不完整或片段编号不匹配：{', '.join(missing)}"
            )
        empty_top_level = [
            field
            for field in ("segment_summary", "segment_script")
            if not str(script.get(field, "")).strip()
        ]
        shots = script.get("storyboard")
        if empty_top_level or not isinstance(shots, list) or not shots:
            details = ", ".join(empty_top_level or ["storyboard"])
            raise ReplicaAnalysisModelError(f"分段脚本含空内容：{details}")
        for order, shot in enumerate(shots, start=1):
            if not isinstance(shot, dict):
                raise ReplicaAnalysisModelError(f"分段脚本第 {order} 个镜头格式不正确")
            empty_fields = [
                field
                for field in cls._required_shot_text_fields
                if not str(shot.get(field, "")).strip()
            ]
            if empty_fields:
                raise ReplicaAnalysisModelError(
                    f"分段脚本第 {order} 个镜头含空字段：{', '.join(empty_fields)}"
                )

    @staticmethod
    def _attach_original_dialogue(script: dict[str, Any], chunk: dict[str, Any]) -> None:
        source_shots = {
            int(shot["order"]): shot
            for shot in chunk["shots"]
            if isinstance(shot, dict) and str(shot.get("order", "")).isdigit()
        }
        for output_shot in script["storyboard"]:
            try:
                order = int(output_shot["order"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ReplicaAnalysisModelError("分段脚本镜头顺序无效") from exc
            source_shot = source_shots.get(order)
            if source_shot is None:
                raise ReplicaAnalysisModelError(f"分段脚本包含不存在的镜头：{order}")
            output_shot["voiceover"] = str(source_shot.get("original_dialogue", "无")) or "无"

    async def _write_segment(
        self,
        job_path: Path,
        chunk: dict[str, Any],
        context: str,
        previous_summary: str,
        prompt_template: StoryboardPromptTemplate,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        content = await asyncio.to_thread(
            self._build_message,
            job_path,
            chunk,
            context,
            previous_summary,
            prompt_template,
        )
        return await self.client.complete_json(
            system_prompt=prompt_template.system_prompt,
            content=content,
            max_tokens=3000,
            timeout_seconds=180,
            temperature=0.1,
            log_context=f"分段分镜脚本 analysis_id={job_path.name} segment_id={chunk['segment_id']}",
        )

    def _build_message(
        self,
        job_path: Path,
        chunk: dict[str, Any],
        context: str,
        previous_summary: str,
        prompt_template: StoryboardPromptTemplate,
    ) -> list[dict[str, Any]]:
        instructions = {
            "segment_id": chunk["segment_id"],
            "time_range_ms": [chunk["start_ms"], chunk["end_ms"]],
            "duration_ms": chunk["duration_ms"],
            "video_context": context or "无",
            "previous_segment_summary": previous_summary,
            "shots": [
                {
                    "order": shot["order"],
                    "source_scene_id": shot["scene_id"],
                    "time_range_ms": [shot["start_ms"], shot["end_ms"]],
                    "forced_split": shot["forced_split"],
                    "frame_count": len(shot["frame_paths"]),
                    "primary_transcript": "；".join(shot["primary_transcript"]) or "无",
                    "context_transcript": "；".join(shot["context_transcript"]) or "无",
                    "original_dialogue": shot["original_dialogue"],
                }
                for shot in chunk["shots"]
            ],
            "required_json": prompt_template.response_schema,
        }
        contact_sheet = (job_path / str(chunk["contact_sheet"])).resolve()
        try:
            contact_sheet.relative_to(job_path)
        except ValueError as exc:
            raise ReplicaAnalysisNotReadyError("拼接分镜图路径无效") from exc
        if not contact_sheet.is_file():
            raise ReplicaAnalysisNotReadyError("拼接分镜图不存在，请重新生成分段脚本")
        image = base64.b64encode(contact_sheet.read_bytes()).decode("ascii")
        return [
            {"type": "text", "text": json.dumps(instructions, ensure_ascii=False)},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image}", "detail": "high"},
            },
        ]
