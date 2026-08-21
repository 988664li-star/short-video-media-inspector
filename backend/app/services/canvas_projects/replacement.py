"""Visual analysis for identifying replaceable subjects across canvas shots."""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO
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
    """Extract durable shot anchors, then analyse compact numbered contact sheets once."""

    _CONTACT_SHEET_COLUMNS = 3
    _CONTACT_SHEET_ROWS = 2
    _CONTACT_SHEET_TILE_SIZE = (320, 568)

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

    def _vision_content(
        self,
        project_id: str,
        keyframes: list[dict[str, Any]],
        instruction: str,
    ) -> list[dict[str, Any]]:
        contact_sheets = self._contact_sheets(project_id, keyframes)
        content: list[dict[str, Any]] = [{
            "type": "text",
            "text": instruction,
        }]
        for contact_sheet in contact_sheets:
            encoded = base64.b64encode(contact_sheet).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "high"},
            })
        return content

    def _contact_sheets(self, project_id: str, keyframes: list[dict[str, Any]]) -> list[bytes]:
        capacity = self._CONTACT_SHEET_COLUMNS * self._CONTACT_SHEET_ROWS
        sheets: list[bytes] = []
        for offset in range(0, len(keyframes), capacity):
            batch = keyframes[offset:offset + capacity]
            tile_width, tile_height = self._CONTACT_SHEET_TILE_SIZE
            canvas = Image.new(
                "RGB",
                (tile_width * self._CONTACT_SHEET_COLUMNS, tile_height * self._CONTACT_SHEET_ROWS),
                "#0b1420",
            )
            draw = ImageDraw.Draw(canvas)
            for position, item in enumerate(batch):
                try:
                    _, path = self.project_service.get_asset_file(project_id, item["asset"]["id"])
                except CanvasAssetNotFoundError as exc:
                    raise CanvasReplacementAnalysisError("分析关键帧保存失败") from exc
                try:
                    with Image.open(path) as source:
                        image = source.convert("RGB")
                except OSError as exc:
                    raise CanvasReplacementAnalysisError("分析关键帧无法拼接") from exc
                image.thumbnail((tile_width, tile_height))
                column = position % self._CONTACT_SHEET_COLUMNS
                row = position // self._CONTACT_SHEET_COLUMNS
                origin_x = column * tile_width
                origin_y = row * tile_height
                canvas.paste(image, (
                    origin_x + (tile_width - image.width) // 2,
                    origin_y + (tile_height - image.height) // 2,
                ))
                draw.rectangle((origin_x + 10, origin_y + 10, origin_x + 104, origin_y + 38), fill="#06101b")
                draw.text((origin_x + 16, origin_y + 16), str(item["shot_index"]), fill="#ffffff")
            output = BytesIO()
            canvas.save(output, format="JPEG", quality=82, optimize=True)
            sheets.append(output.getvalue())
        return sheets

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
