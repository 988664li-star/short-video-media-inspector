"""Whole-video replica playbook generation from completed storyboard scripts."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from backend.app.services.replica_analysis.common import (
    ReplicaAnalysisModelError,
    ReplicaAnalysisNotReadyError,
    job_path,
    read_json,
    write_json,
)
from backend.app.services.replica_analysis.templates import ReplicaPromptTemplate
from backend.app.services.siliconflow import SiliconFlowClient, SiliconFlowError


class ReplicaPlaybookService:
    """Build one source-video replacement plan from storyboard evidence."""

    _playbook_version = 2

    def __init__(
        self,
        data_path: Path,
        client: SiliconFlowClient,
        prompt_template: ReplicaPromptTemplate | None = None,
    ) -> None:
        self.data_path = data_path
        self.client = client
        self.prompt_template = prompt_template
        self._job_lock = asyncio.Lock()

    async def build(
        self,
        analysis_id: str,
        packages: dict[str, Any],
        storyboard_scripts: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._job_lock:
            target = job_path(self.data_path, analysis_id)
            output_path = target / "replica_playbook.json"
            cached = read_json(output_path)
            if (
                cached is not None
                and cached.get("playbook_version") == self._playbook_version
                and cached.get("source_storyboard_scripts")
                == "storyboard_chunks/scripts.json"
            ):
                return {**cached, "cached": True}
            if not packages.get("scene_packages"):
                raise ReplicaAnalysisNotReadyError("自动分镜素材不完整，请重新识别")
            segments = storyboard_scripts.get("segments", [])
            if not isinstance(segments, list) or not segments:
                raise ReplicaAnalysisNotReadyError("分段分镜脚本尚未完成")

            prompt_template = self.prompt_template or ReplicaPromptTemplate.load(
                "replica_playbook.md", "replica_playbook_schema.json"
            )
            source = {
                "scene_packages": packages["scene_packages"],
                "storyboard_scripts": segments,
            }
            content = "输入数据：\n" + json.dumps(
                source, ensure_ascii=False
            ) + "\n\n返回结构：\n" + json.dumps(
                prompt_template.response_schema, ensure_ascii=False
            )
            try:
                playbook, usage = await self.client.complete_json(
                    system_prompt=prompt_template.system_prompt,
                    content=content,
                    max_tokens=4000,
                    timeout_seconds=180,
                    temperature=0.2,
                    log_context=f"替换方案 analysis_id={analysis_id}",
                )
            except SiliconFlowError as exc:
                raise ReplicaAnalysisModelError(str(exc)) from exc
            result = {
                "analysis_id": analysis_id,
                "playbook_version": self._playbook_version,
                "source_packages": "scene_packages.json",
                "source_storyboard_scripts": "storyboard_chunks/scripts.json",
                "model": self.client.config.model,
                "playbook": playbook,
                "usage": usage,
            }
            await asyncio.to_thread(write_json, output_path, result)
            return {**result, "cached": False}

    def load(self, analysis_id: str) -> dict[str, Any]:
        """Read an existing replacement plan without invoking the visual model."""
        target = job_path(self.data_path, analysis_id)
        payload = read_json(target / "replica_playbook.json")
        if payload is None or not isinstance(payload.get("playbook"), dict):
            raise ReplicaAnalysisNotReadyError("替换方案尚未生成")
        return payload
