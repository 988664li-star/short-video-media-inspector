"""Visual analysis for identifying replaceable subjects across canvas shots."""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from pathlib import Path
from typing import Any

import av

from backend.app.services.siliconflow import SiliconFlowClient, SiliconFlowError

from .service import CanvasAssetNotFoundError, CanvasProjectService


class CanvasReplacementAnalysisError(RuntimeError):
    """The canvas could not identify editable subjects in the source shots."""


class CanvasReplacementAnalysisService:
    """Extract one durable visual anchor per shot and analyse it with a vision model."""

    def __init__(self, project_service: CanvasProjectService, vision_client: SiliconFlowClient) -> None:
        self.project_service = project_service
        self.vision_client = vision_client

    async def analyze(self, project_id: str, shots: list[dict[str, Any]]) -> dict[str, Any]:
        keyframes = await asyncio.to_thread(self._extract_keyframes, project_id, shots)
        if not keyframes:
            raise CanvasReplacementAnalysisError("没有提取到可用于对象识别的镜头关键帧")
        try:
            result, _ = await self.vision_client.complete_json(
                system_prompt=(
                    "你是短视频局部替换工作流的视觉分析器。根据按时间顺序提供的镜头关键帧，"
                    "识别可替换的主体，并将同一对象跨镜头合并为一个对象。可替换对象包括商品、人物、"
                    "背景、屏幕或画面文字，以及其他清晰的独立对象。不要把手、桌面、光线等普通组成部分"
                    "单独列为对象，除非它们是画面明确要替换的主体。"
                    "必须只返回 JSON 对象，包含 objects 数组。每个对象字段："
                    "kind（product/person/background/text/other）、name、description、shot_indices、actions。"
                    "actions 是数组，每项含 shot_index 和 description；description 要说明该对象在该镜头的"
                    "位置、状态、人物交互或镜头表现，供后续逐镜头替换提示词使用。"
                    "同一件商品或同一人物务必合并，shot_indices 按升序且只包含实际出现的镜头。"
                ),
                content=self._vision_content(project_id, keyframes),
                max_tokens=4_096,
                timeout_seconds=180,
                temperature=0.1,
                log_context="canvas.replacement.analyze",
                enable_thinking=False,
            )
        except SiliconFlowError as exc:
            raise CanvasReplacementAnalysisError(str(exc)) from exc

        return {
            "keyframes": keyframes,
            "objects": self._normalise_objects(result, {item["shot_index"] for item in keyframes}),
        }

    def _extract_keyframes(self, project_id: str, shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        extracted: list[dict[str, Any]] = []
        for shot in sorted(shots, key=lambda item: int(item["index"])):
            try:
                asset, source_path = self.project_service.get_asset_file(project_id, str(shot["asset_id"]))
            except CanvasAssetNotFoundError as exc:
                raise CanvasReplacementAnalysisError(
                    f"镜头 {int(shot['index']):02d} 的本地视频片段不存在，请重新执行按镜头分段"
                ) from exc
            if not str(asset.get("mime_type") or "").startswith("video/"):
                raise CanvasReplacementAnalysisError(f"镜头 {int(shot['index']):02d} 不是可分析的视频片段")
            image_bytes = self._representative_frame(source_path)
            frame_asset = self.project_service.save_asset(
                project_id,
                f"{Path(str(shot['asset_name'])).stem}-analysis-frame.jpg",
                "image/jpeg",
                image_bytes,
            )
            extracted.append({
                "shot_index": int(shot["index"]),
                "asset": frame_asset,
            })
        return extracted

    @staticmethod
    def _representative_frame(source_path: Path) -> bytes:
        try:
            with av.open(str(source_path)) as container:
                stream = container.streams.video[0]
                duration = float(stream.duration * stream.time_base) if stream.duration else 0.0
                target_time = duration * 0.5 if duration > 0 else 0.0
                selected = None
                for frame in container.decode(stream):
                    selected = frame
                    if frame.time is not None and float(frame.time) >= target_time:
                        break
        except (av.error.FFmpegError, IndexError, OSError) as exc:
            raise CanvasReplacementAnalysisError(f"无法读取镜头关键帧：{exc}") from exc
        if selected is None:
            raise CanvasReplacementAnalysisError("镜头中没有可用画面")
        image = selected.to_image().convert("RGB")
        image.thumbnail((960, 960))
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=84, optimize=True)
        return buffer.getvalue()

    def _vision_content(self, project_id: str, keyframes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{
            "type": "text",
            "text": (
                "以下图片按镜头顺序给出。图片序号和镜头编号一一对应："
                + "、".join(str(item["shot_index"]) for item in keyframes)
                + "。请识别同一主体跨镜头的连续出现情况。"
            ),
        }]
        for item in keyframes:
            try:
                _, path = self.project_service.get_asset_file(project_id, item["asset"]["id"])
            except CanvasAssetNotFoundError as exc:
                raise CanvasReplacementAnalysisError("分析关键帧保存失败") from exc
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "high"},
            })
        return content

    @staticmethod
    def _normalise_objects(result: dict[str, Any], valid_shots: set[int]) -> list[dict[str, Any]]:
        raw_objects = result.get("objects") if isinstance(result, dict) else None
        if not isinstance(raw_objects, list):
            raise CanvasReplacementAnalysisError("视觉模型没有返回可替换对象列表")
        allowed_kinds = {"product", "person", "background", "text", "other"}
        objects: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_objects[:40], start=1):
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or "other").lower()
            if kind not in allowed_kinds:
                kind = "other"
            name = str(raw.get("name") or "").strip()[:160]
            if not name:
                continue
            shot_indices = sorted({
                int(item) for item in raw.get("shot_indices", [])
                if isinstance(item, int) and item in valid_shots
            })
            if not shot_indices:
                continue
            actions: list[dict[str, Any]] = []
            raw_actions = raw.get("actions")
            if isinstance(raw_actions, list):
                for action in raw_actions:
                    if not isinstance(action, dict):
                        continue
                    shot_index = action.get("shot_index")
                    description = str(action.get("description") or "").strip()[:1_000]
                    if isinstance(shot_index, int) and shot_index in shot_indices and description:
                        actions.append({"shot_index": shot_index, "description": description})
            action_shots = {item["shot_index"] for item in actions}
            actions.extend({
                "shot_index": shot_index,
                "description": f"{name} 出现在当前镜头中，保持原有位置、动作与遮挡关系。",
            } for shot_index in shot_indices if shot_index not in action_shots)
            objects.append({
                "id": f"object-{index}",
                "kind": kind,
                "name": name,
                "description": str(raw.get("description") or "").strip()[:2_000],
                "shot_indices": shot_indices,
                "actions": sorted(actions, key=lambda item: item["shot_index"]),
            })
        if not objects:
            raise CanvasReplacementAnalysisError("没有识别到可替换对象；可调整视频内容后重新分析")
        return objects
