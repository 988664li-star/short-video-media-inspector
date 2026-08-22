"""Visual analysis for identifying replaceable subjects across canvas shots."""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO
import json
import math
from pathlib import Path
import re
from typing import Any

import av
from PIL import Image, ImageDraw

from backend.app.services.siliconflow import (
    SiliconFlowClient,
    SiliconFlowError,
    SiliconFlowTransportError,
)

from .prompts import CanvasPromptTemplateError, CanvasPromptTemplates
from .service import CanvasAssetNotFoundError, CanvasProjectService


class CanvasReplacementAnalysisError(RuntimeError):
    """The canvas could not identify editable subjects in the source shots."""


class CanvasReplacementAnalysisProviderError(CanvasReplacementAnalysisError):
    """The external vision provider could not complete the analysis request."""


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

    async def analyze(
        self,
        project_id: str,
        shots: list[dict[str, Any]],
        *,
        source_context: str = "",
    ) -> dict[str, Any]:
        keyframes = await asyncio.to_thread(self._extract_keyframes, project_id, shots)
        if not keyframes:
            raise CanvasReplacementAnalysisError("没有提取到可用于对象识别的镜头关键帧")
        try:
            prompt_templates = self.prompt_templates or CanvasPromptTemplates.load()
        except CanvasPromptTemplateError as exc:
            raise CanvasReplacementAnalysisError(str(exc)) from exc
        try:
            observations = await self._analyze_each_shot(
                project_id,
                keyframes,
                prompt_templates,
                source_context,
            )
            if not observations:
                raise CanvasReplacementAnalysisError(
                    "没有识别到具有明确帧证据的可替换主体；可调整视频内容后重新分析"
                )

            merge_result: dict[str, Any] = {"groups": []}
            if len(keyframes) > 1 and len(observations) > 1:
                merge_result, _ = await self._complete_json_with_retry(
                    system_prompt=prompt_templates.replacement_analysis_merge_system,
                    content=prompt_templates.render_replacement_analysis_merge(
                        json.dumps(observations, ensure_ascii=False),
                    ),
                    max_tokens=4_096,
                    timeout_seconds=180,
                    temperature=0.0,
                    log_context="canvas.replacement.merge",
                )
            objects = self._merge_observations(merge_result, observations)
        except CanvasPromptTemplateError as exc:
            raise CanvasReplacementAnalysisError(str(exc)) from exc
        except SiliconFlowError as exc:
            raise CanvasReplacementAnalysisProviderError(str(exc)) from exc

        return {
            "keyframes": keyframes,
            "objects": objects,
        }

    async def _analyze_each_shot(
        self,
        project_id: str,
        keyframes: list[dict[str, Any]],
        prompt_templates: CanvasPromptTemplates,
        source_context: str,
    ) -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(4)

        async def analyze_one(keyframe: dict[str, Any]) -> list[dict[str, Any]]:
            shot_index = int(keyframe["shot_index"])
            async with semaphore:
                result, _ = await self._complete_json_with_retry(
                    system_prompt=prompt_templates.replacement_analysis_system,
                    content=self._vision_content(
                        project_id,
                        [keyframe],
                        prompt_templates.replacement_analysis_user,
                        source_context,
                    ),
                    max_tokens=4_096,
                    timeout_seconds=180,
                    temperature=0.1,
                    log_context=f"canvas.replacement.analyze.shot-{shot_index:02d}",
                )
            return self._normalise_shot_observations(result, shot_index)

        results = await asyncio.gather(*(analyze_one(keyframe) for keyframe in keyframes))
        return [observation for shot_result in results for observation in shot_result]

    async def _complete_json_with_retry(self, **request: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        for attempt in range(2):
            try:
                return await self.vision_client.complete_json(**request)
            except SiliconFlowTransportError:
                if attempt == 1:
                    raise
                await asyncio.sleep(1.0)
        raise AssertionError("视觉模型重试流程异常结束")

    @staticmethod
    def _normalise_shot_observations(
        result: dict[str, Any],
        shot_index: int,
    ) -> list[dict[str, Any]]:
        raw_objects = result.get("objects") if isinstance(result, dict) else None
        if not isinstance(raw_objects, list):
            raise CanvasReplacementAnalysisError("视觉模型没有返回单片段主体观察列表")

        allowed_kinds = {"product", "person", "background", "text", "other"}
        observations: list[dict[str, Any]] = []
        for raw in raw_objects:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()[:160]
            action = str(raw.get("action") or "").strip()[:1_000]
            if not name or not action:
                continue
            if not re.search(r"(?:帧\s*[1-6]|第\s*[1-6]\s*帧)", action):
                continue
            kind = str(raw.get("kind") or "other").lower()
            if kind not in allowed_kinds:
                kind = "other"
            observations.append({
                "observation_id": f"shot-{shot_index}-object-{len(observations) + 1}",
                "shot_index": shot_index,
                "kind": kind,
                "name": name,
                "description": str(raw.get("description") or "").strip()[:2_000],
                "action": action,
            })
        return observations

    @staticmethod
    def _observations_can_merge(observations: list[dict[str, Any]]) -> bool:
        if len(observations) < 2:
            return True
        kinds = {str(item["kind"]) for item in observations}
        if len(kinds) != 1:
            return False
        names = [
            re.sub(r"[^\w\u4e00-\u9fff]+", "", str(item["name"])).casefold()
            for item in observations
        ]
        shortest_name = min(names, key=len)
        if shortest_name and all(shortest_name in name or name in shortest_name for name in names):
            return True
        if kinds == {"person"}:
            person_markers = ("模特", "人物", "达人", "演员", "手模", "脚模")
            return any(all(marker in name for name in names) for marker in person_markers)
        return False

    @staticmethod
    def _merge_observations(
        result: dict[str, Any],
        observations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        observation_by_id = {
            str(item["observation_id"]): item
            for item in observations
        }
        allowed_kinds = {"product", "person", "background", "text", "other"}
        claimed_ids: set[str] = set()
        accepted_groups: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
        raw_groups = result.get("groups") if isinstance(result, dict) else None

        if isinstance(raw_groups, list):
            for raw_group in raw_groups:
                if not isinstance(raw_group, dict):
                    continue
                raw_ids = raw_group.get("observation_ids")
                if not isinstance(raw_ids, list):
                    continue
                group_observations: list[dict[str, Any]] = []
                group_shots: set[int] = set()
                for raw_id in raw_ids:
                    observation_id = str(raw_id)
                    observation = observation_by_id.get(observation_id)
                    if observation is None or observation_id in claimed_ids:
                        continue
                    shot_index = int(observation["shot_index"])
                    if shot_index in group_shots:
                        continue
                    group_observations.append(observation)
                    group_shots.add(shot_index)
                if not group_observations:
                    continue
                if not CanvasReplacementAnalysisService._observations_can_merge(group_observations):
                    for observation in group_observations:
                        claimed_ids.add(str(observation["observation_id"]))
                        accepted_groups.append(([observation], {}))
                    continue
                for observation in group_observations:
                    claimed_ids.add(str(observation["observation_id"]))
                accepted_groups.append((group_observations, raw_group))

        # If the merge model omits an observation, retain it instead of silently
        # losing a visually verified subject. Exact same-name observations may be
        # safely consolidated without inventing a new shot relationship.
        fallback_groups: dict[tuple[str, str], list[list[dict[str, Any]]]] = {}
        for observation in observations:
            observation_id = str(observation["observation_id"])
            if observation_id in claimed_ids:
                continue
            key = (
                str(observation["kind"]),
                re.sub(r"\s+", "", str(observation["name"])).casefold(),
            )
            candidate_groups = fallback_groups.setdefault(key, [])
            target_group = next((
                group
                for group in candidate_groups
                if all(item["shot_index"] != observation["shot_index"] for item in group)
            ), None)
            if target_group is None:
                candidate_groups.append([observation])
            else:
                target_group.append(observation)
        accepted_groups.extend(
            (items, {})
            for groups in fallback_groups.values()
            for items in groups
        )

        objects: list[dict[str, Any]] = []
        for group_observations, raw_group in accepted_groups:
            first = group_observations[0]
            proposed_kind = str(raw_group.get("kind") or first["kind"]).lower()
            kind = proposed_kind if proposed_kind in allowed_kinds else str(first["kind"])
            name = str(raw_group.get("name") or first["name"]).strip()[:160] or str(first["name"])
            description = (
                str(raw_group.get("description") or "").strip()[:2_000]
                or str(first.get("description") or "")
            )
            ordered = sorted(group_observations, key=lambda item: int(item["shot_index"]))
            objects.append({
                "id": f"object-{len(objects) + 1}",
                "kind": kind,
                "name": name,
                "description": description,
                "shot_indices": [int(item["shot_index"]) for item in ordered],
                "actions": [
                    {
                        "shot_index": int(item["shot_index"]),
                        "description": str(item["action"]),
                    }
                    for item in ordered
                ],
            })

        if not objects:
            raise CanvasReplacementAnalysisError("没有可归并的主体观察结果")
        return objects

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
        source_context: str = "",
    ) -> list[dict[str, Any]]:
        clean_context = source_context.strip()[:4_000]
        context_instruction = (
            "\n\n来源作品标题/发布文案（用于判断商品类别和专有名称，解决外观相似对象的歧义；"
            "若与画面明确事实冲突，以画面为准，不得虚构画面中不存在的主体）：\n"
            f"{clean_context}"
            if clean_context
            else ""
        )
        content: list[dict[str, Any]] = [{
            "type": "text",
            "text": f"{instruction}{context_instruction}",
        }]
        for item in sorted(keyframes, key=lambda frame: int(frame["shot_index"])):
            try:
                _, path = self.project_service.get_asset_file(project_id, item["asset"]["id"])
                image_bytes = path.read_bytes()
            except (CanvasAssetNotFoundError, OSError) as exc:
                raise CanvasReplacementAnalysisError("编辑片段分镜图读取失败") from exc
            encoded = base64.b64encode(image_bytes).decode("ascii")
            content.append({
                "type": "text",
                "text": (
                    f"服务器确认：下面这张六宫格只属于片段 {int(item['shot_index'])}。"
                    "请只报告图中有具体帧号证据的主体。"
                ),
            })
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "high"},
            })
        return content
