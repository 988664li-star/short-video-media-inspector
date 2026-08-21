"""Visual analysis for identifying replaceable subjects across canvas shots."""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO
import math
from pathlib import Path
from typing import Any

import av
from PIL import Image, ImageDraw

from backend.app.services.siliconflow import SiliconFlowClient, SiliconFlowError

from .prompts import CanvasPromptTemplateError, CanvasPromptTemplates
from .service import CanvasAssetNotFoundError, CanvasProjectService


class CanvasReplacementAnalysisError(RuntimeError):
    """The canvas could not identify editable subjects in the source shots."""


class CanvasReplacementAnalysisService:
    """Analyse each contiguous edit segment as a short temporal storyboard."""

    _STORYBOARD_FRAME_COUNT = 6
    _STORYBOARD_COLUMNS = 3

    def __init__(
        self,
        project_service: CanvasProjectService,
        vision_client: SiliconFlowClient,
        prompt_templates: CanvasPromptTemplates | None = None,
    ) -> None:
        self.project_service = project_service
        self.vision_client = vision_client
        self.prompt_templates = prompt_templates

    async def analyze(self, project_id: str, shots: list[dict[str, Any]]) -> dict[str, Any]:
        keyframes = await asyncio.to_thread(self._extract_keyframes, project_id, shots)
        if not keyframes:
            raise CanvasReplacementAnalysisError("没有提取到可用于对象识别的镜头关键帧")
        try:
            prompt_templates = self.prompt_templates or CanvasPromptTemplates.load()
        except CanvasPromptTemplateError as exc:
            raise CanvasReplacementAnalysisError(str(exc)) from exc
        try:
            result, _ = await self.vision_client.complete_json(
                system_prompt=prompt_templates.replacement_analysis_system,
                content=self._vision_content(
                    project_id,
                    keyframes,
                    prompt_templates.replacement_analysis_user,
                ),
                max_tokens=4_096,
                timeout_seconds=180,
                temperature=0.1,
                log_context="canvas.replacement.analyze",
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
            image_bytes = self._segment_storyboard(source_path)
            frame_asset = self.project_service.save_asset(
                project_id,
                f"{Path(str(shot['asset_name'])).stem}-analysis-storyboard.jpg",
                "image/jpeg",
                image_bytes,
            )
            extracted.append({
                "shot_index": int(shot["index"]),
                "asset": frame_asset,
            })
        return extracted

    @classmethod
    def _segment_storyboard(cls, source_path: Path) -> bytes:
        try:
            with av.open(str(source_path)) as container:
                stream = container.streams.video[0]
                duration = float(stream.duration * stream.time_base) if stream.duration else 0.0
                targets = [
                    duration * index / (cls._STORYBOARD_FRAME_COUNT - 1)
                    for index in range(cls._STORYBOARD_FRAME_COUNT)
                ]
                selected: list[Image.Image] = []
                target_index = 0
                last_image: Image.Image | None = None
                for frame in container.decode(stream):
                    timestamp = float(frame.time) if frame.time is not None else 0.0
                    image = frame.to_image().convert("RGB")
                    last_image = image
                    while target_index < len(targets) and timestamp >= targets[target_index]:
                        selected.append(image.copy())
                        target_index += 1
                if last_image is not None:
                    selected.extend(last_image.copy() for _ in range(len(targets) - len(selected)))
        except (av.error.FFmpegError, IndexError, OSError) as exc:
            raise CanvasReplacementAnalysisError(f"无法读取镜头关键帧：{exc}") from exc
        if not selected:
            raise CanvasReplacementAnalysisError("镜头中没有可用画面")
        first = selected[0]
        tile_width = 360
        tile_height = max(200, round(tile_width * first.height / first.width))
        gutter = 8
        label_height = 30
        rows = math.ceil(cls._STORYBOARD_FRAME_COUNT / cls._STORYBOARD_COLUMNS)
        storyboard = Image.new(
            "RGB",
            (
                cls._STORYBOARD_COLUMNS * tile_width + (cls._STORYBOARD_COLUMNS + 1) * gutter,
                rows * (tile_height + label_height) + (rows + 1) * gutter,
            ),
            "#101722",
        )
        draw = ImageDraw.Draw(storyboard)
        for index, source in enumerate(selected[:cls._STORYBOARD_FRAME_COUNT]):
            image = source.copy()
            image.thumbnail((tile_width, tile_height))
            column = index % cls._STORYBOARD_COLUMNS
            row = index // cls._STORYBOARD_COLUMNS
            origin_x = gutter + column * (tile_width + gutter)
            origin_y = gutter + row * (tile_height + label_height + gutter)
            storyboard.paste(
                image,
                (origin_x + (tile_width - image.width) // 2, origin_y + (tile_height - image.height) // 2),
            )
            draw.text((origin_x + 8, origin_y + tile_height + 7), f"帧 {index + 1}", fill="#ffffff")
        buffer = BytesIO()
        storyboard.save(buffer, format="JPEG", quality=88, optimize=True)
        return buffer.getvalue()

    def _vision_content(
        self,
        project_id: str,
        keyframes: list[dict[str, Any]],
        instruction: str,
    ) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{
            "type": "text",
            "text": instruction,
        }]
        for item in sorted(keyframes, key=lambda frame: int(frame["shot_index"])):
            try:
                _, path = self.project_service.get_asset_file(project_id, item["asset"]["id"])
                image_bytes = path.read_bytes()
            except (CanvasAssetNotFoundError, OSError) as exc:
                raise CanvasReplacementAnalysisError("编辑片段分镜图读取失败") from exc
            encoded = base64.b64encode(image_bytes).decode("ascii")
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
        for index, raw in enumerate(raw_objects[:3], start=1):
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or "other").lower()
            if kind not in allowed_kinds:
                kind = "other"
            name = str(raw.get("name") or "").strip()[:160]
            if not name:
                continue
            raw_shot_indices = raw.get("shot_indices", [])
            if not all(isinstance(item, int) and not isinstance(item, bool) for item in raw_shot_indices):
                raise CanvasReplacementAnalysisError(
                    f"主体“{name}”的 shot_indices 必须使用整数镜头号，例如 [1, 2]，不能使用 SHOT01"
                )
            shot_indices = sorted({item for item in raw_shot_indices if item in valid_shots})
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
                    if isinstance(shot_index, int) and not isinstance(shot_index, bool) and shot_index in shot_indices and description:
                        actions.append({"shot_index": shot_index, "description": description})
            action_shots = {item["shot_index"] for item in actions}
            actions.extend({
                "shot_index": shot_index,
                "description": f"{name} 出现在当前连续片段中，保持原有位置、动作与遮挡关系。",
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
