"""Provider-neutral, per-shot replacement orchestration for the creative canvas."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from io import BytesIO
import json
import logging
import math
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import av
import httpx
from PIL import Image, ImageDraw

from backend.app.services.siliconflow import SiliconFlowClient, SiliconFlowError

from backend.app.services.video_generation import (
    VideoAssetPublisher,
    VideoAssetPublisherError,
    VideoEditRequest,
    VideoGenerationProvider,
    VideoGenerationProviderError,
    VideoGenerationRegistry,
    VideoModelProfile,
    VideoProviderContext,
)
from .prompts import CanvasPromptTemplateError, CanvasPromptTemplates
from .service import CanvasAssetNotFoundError, CanvasProjectService


logger = logging.getLogger("uvicorn.error")


MAX_CONCURRENT_SUBMISSIONS = 3
MAX_CONCURRENT_PROMPT_COMPOSITIONS = 3


class CanvasReplacementTaskError(RuntimeError):
    """A per-shot canvas replacement task could not be prepared or submitted."""


@dataclass(frozen=True)
class CanvasReplacementVideoConfig:
    max_asset_bytes: int


class CanvasReplacementTaskService:
    """Render, submit and refresh explicit per-shot video replacement tasks.

    This service is intentionally independent from the older continuous-segment
    provider-specific workspace. A canvas task always has one contiguous source
    video edit segment and one or more target reference images.
    """

    def __init__(
        self,
        project_service: CanvasProjectService,
        object_storage: VideoAssetPublisher,
        config: CanvasReplacementVideoConfig,
        vision_client: SiliconFlowClient,
        prompt_templates: CanvasPromptTemplates | None = None,
        provider_registry: VideoGenerationRegistry | None = None,
    ) -> None:
        self.project_service = project_service
        self.object_storage = object_storage
        self.config = config
        self.vision_client = vision_client
        self.prompt_templates = prompt_templates
        self.provider_registry = provider_registry or VideoGenerationRegistry([])

    def available_models(self) -> list[dict[str, object]]:
        return self.provider_registry.catalog("subject_replace")

    async def build_prompts(
        self,
        *,
        project_id: str,
        source_object_name: str,
        source_object_description: str,
        target_description: str,
        target_asset_ids: list[str],
        shots: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        subjects: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if not target_asset_ids:
            raise CanvasReplacementTaskError("请先连接至少一张目标对象参考图")
        try:
            template = self.prompt_templates or CanvasPromptTemplates.load()
        except CanvasPromptTemplateError as exc:
            raise CanvasReplacementTaskError(str(exc)) from exc
        prompt_subjects = subjects or []
        subject_references: list[tuple[dict[str, Any], list[str]]] = []
        if prompt_subjects:
            ordered_subject_asset_ids: list[str] = []
            for subject in prompt_subjects:
                subject_asset_ids = list(subject.get("target_asset_ids") or [])
                if not subject_asset_ids:
                    raise CanvasReplacementTaskError(
                        f"替换主体“{subject.get('source_object_name') or '未命名主体'}”缺少目标参考图"
                    )
                subject_references.append((
                    subject,
                    subject_asset_ids,
                ))
                ordered_subject_asset_ids.extend(subject_asset_ids)
            if ordered_subject_asset_ids != target_asset_ids:
                raise CanvasReplacementTaskError(
                    "主体与目标图片的绑定顺序不一致，请重新生成视频编辑指令"
                )
            if len(ordered_subject_asset_ids) > 8:
                raise CanvasReplacementTaskError("一次多主体替换最多使用 8 张目标参考图")
        else:
            action_by_shot = {
                int(item["shot_index"]): str(item["description"])
                for item in actions
                if isinstance(item, dict) and isinstance(item.get("shot_index"), int)
            }
            subject_references = [(
                {
                    "source_object_name": source_object_name,
                    "source_object_description": source_object_description,
                    "target_description": target_description,
                    "actions": [
                        {"shot_index": index, "description": description}
                        for index, description in action_by_shot.items()
                    ],
                },
                target_asset_ids,
            )]

        reference_images = await self._load_reference_images(project_id, target_asset_ids)
        target_image_references = {
            asset_id: f"@图片{index}"
            for index, asset_id in enumerate(target_asset_ids, start=1)
        }
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROMPT_COMPOSITIONS)

        async def compose_shot(shot: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await self._compose_multimodal_prompt(
                    project_id=project_id,
                    shot=shot,
                    subject_references=subject_references,
                    reference_images=reference_images,
                    target_image_references=target_image_references,
                    template=template,
                )

        prompts = await asyncio.gather(*[
            compose_shot(shot)
            for shot in sorted(shots, key=lambda item: int(item["index"]))
        ])
        return list(prompts)

    async def _compose_multimodal_prompt(
        self,
        *,
        project_id: str,
        shot: dict[str, Any],
        subject_references: list[tuple[dict[str, Any], list[str]]],
        reference_images: dict[str, dict[str, str]],
        target_image_references: dict[str, str],
        template: CanvasPromptTemplates,
    ) -> dict[str, Any]:
        shot_index = int(shot["index"])
        active_subjects: list[dict[str, Any]] = []
        for subject, asset_ids in subject_references:
            shot_indices = {
                int(index) for index in subject.get("shot_indices") or []
                if isinstance(index, int)
            }
            if shot_indices and shot_index not in shot_indices:
                continue
            actions = {
                int(item["shot_index"]): str(item["description"])
                for item in subject.get("actions") or []
                if isinstance(item, dict) and isinstance(item.get("shot_index"), int)
            }
            subject_name = str(subject.get("source_object_name") or "源视频中的对象")
            active_subjects.append({
                "source_object_name": subject_name,
                "source_object_kind": str(subject.get("source_object_kind") or "product"),
                "source_object_description": str(
                    subject.get("source_object_description") or "源视频中的该对象"
                ),
                "target_description": str(
                    subject.get("target_description")
                    or "以绑定目标素材图片中可见的外观、颜色、材质与结构为准"
                ),
                "appearance_evidence": actions.get(
                    shot_index,
                    f"{subject_name} 出现在当前连续片段中；保持其原有位置、动作与遮挡关系。",
                ),
                "target_image_ids": asset_ids,
                "target_image_names": [reference_images[asset_id]["filename"] for asset_id in asset_ids],
                "seedance_target_images": [target_image_references[asset_id] for asset_id in asset_ids],
            })
        if not active_subjects:
            raise CanvasReplacementTaskError(
                f"片段 {shot_index:02d} 没有可替换主体，请调整替换范围后重试"
            )

        storyboard_data_uri = await asyncio.to_thread(
            self._storyboard_data_uri, project_id, shot
        )
        shot_context = {
            "shot_index": shot_index,
            "duration_seconds": round(float(shot.get("duration_seconds") or 0), 2),
            "source_video_name": str(shot.get("asset_name") or f"片段 {shot_index:02d}"),
            "instruction": "原片段六宫格展示该连续视频的时间顺序；保持其时长、镜头顺序和运动。",
        }
        content: list[dict[str, Any]] = [{
            "type": "text",
            "text": template.render_replacement_video_prompt(
                shot_context_json=json.dumps(shot_context, ensure_ascii=False),
                subjects_json=json.dumps(active_subjects, ensure_ascii=False),
            ),
        }, {
            "type": "text",
            "text": "图片 1：原视频当前连续片段的六宫格分镜图。",
        }, {
            "type": "image_url",
            "image_url": {"url": storyboard_data_uri, "detail": "high"},
        }]
        for subject in active_subjects:
            for asset_id in subject["target_image_ids"]:
                reference = reference_images[asset_id]
                content.extend([{
                    "type": "text",
                    "text": (
                        f"目标素材图：绑定源主体“{subject['source_object_name']}”，"
                        f"文件名为“{reference['filename']}”。只能用于该主体。"
                    ),
                }, {
                    "type": "image_url",
                    "image_url": {"url": reference["data_uri"], "detail": "high"},
                }])
        try:
            result, _ = await self.vision_client.complete_json(
                system_prompt=template.replacement_video_prompt_system,
                content=content,
                max_tokens=2_048,
                timeout_seconds=180,
                temperature=0.1,
                log_context=f"canvas.replacement.prompt.shot-{shot_index:02d}",
            )
        except SiliconFlowError as exc:
            raise CanvasReplacementTaskError(
                f"片段 {shot_index:02d} 的多模态提示词生成失败：{exc}"
            ) from exc
        prompt = str(result.get("prompt") or "").strip()
        if not prompt:
            raise CanvasReplacementTaskError(
                f"片段 {shot_index:02d} 的多模态模型没有返回视频编辑指令"
            )
        warning = str(result.get("warning") or "").strip()
        if warning:
            logger.warning(
                "canvas.video.replacement.prompt.warning project_id=%s shot_index=%02d warning=%s",
                project_id,
                shot_index,
                warning,
            )
        return {
            "shot_index": shot_index,
            "prompt": prompt,
            "input_revision": 5,
            "status": "ready",
        }

    async def _load_reference_images(
        self,
        project_id: str,
        asset_ids: list[str],
    ) -> dict[str, dict[str, str]]:
        references = await asyncio.gather(*[
            asyncio.to_thread(self._reference_image_payload, project_id, asset_id)
            for asset_id in dict.fromkeys(asset_ids)
        ])
        return {asset_id: reference for asset_id, reference in zip(dict.fromkeys(asset_ids), references)}

    def _reference_image_payload(self, project_id: str, asset_id: str) -> dict[str, str]:
        try:
            asset, path = self.project_service.get_asset_file(project_id, asset_id)
        except CanvasAssetNotFoundError as exc:
            raise CanvasReplacementTaskError(f"目标素材不存在：{asset_id}") from exc
        mime_type = str(asset.get("mime_type") or "").lower()
        if mime_type not in {"image/jpeg", "image/jpg", "image/png", "image/webp"}:
            raise CanvasReplacementTaskError(f"目标素材不是支持的图片格式：{asset.get('filename')}")
        try:
            image_bytes = path.read_bytes()
        except OSError as exc:
            raise CanvasReplacementTaskError(f"目标素材读取失败：{asset.get('filename')}") from exc
        return {
            "filename": str(asset.get("filename") or asset_id),
            "data_uri": f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}",
        }

    def _storyboard_data_uri(self, project_id: str, shot: dict[str, Any]) -> str:
        shot_index = int(shot["index"])
        try:
            asset, source_path = self.project_service.get_asset_file(
                project_id, str(shot["asset_id"])
            )
        except CanvasAssetNotFoundError as exc:
            raise CanvasReplacementTaskError(f"片段 {shot_index:02d} 的源视频不存在") from exc
        if not str(asset.get("mime_type") or "").startswith("video/"):
            raise CanvasReplacementTaskError(f"片段 {shot_index:02d} 不是视频素材")
        try:
            image_bytes = self._make_storyboard(source_path)
        except (av.error.FFmpegError, IndexError, OSError) as exc:
            raise CanvasReplacementTaskError(f"片段 {shot_index:02d} 的分镜图生成失败：{exc}") from exc
        return f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode('ascii')}"

    @staticmethod
    def _make_storyboard(source_path: Path) -> bytes:
        frame_count = 6
        columns = 3
        with av.open(str(source_path)) as container:
            stream = container.streams.video[0]
            duration = float(stream.duration * stream.time_base) if stream.duration else 0.0
            targets = [duration * index / (frame_count - 1) for index in range(frame_count)]
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
                selected.extend(last_image.copy() for _ in range(frame_count - len(selected)))
        if not selected:
            raise OSError("视频中没有可用画面")
        first = selected[0]
        tile_width = 360
        tile_height = max(200, round(tile_width * first.height / first.width))
        gutter = 8
        label_height = 30
        rows = math.ceil(frame_count / columns)
        storyboard = Image.new(
            "RGB",
            (
                columns * tile_width + (columns + 1) * gutter,
                rows * (tile_height + label_height) + (rows + 1) * gutter,
            ),
            "#101722",
        )
        draw = ImageDraw.Draw(storyboard)
        for index, source in enumerate(selected[:frame_count]):
            image = source.copy()
            image.thumbnail((tile_width, tile_height))
            column = index % columns
            row = index // columns
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

    async def submit(
        self,
        project_id: str,
        *,
        model: str,
        target_asset_ids: list[str],
        shots: list[dict[str, Any]],
        prompts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        submit_started = time.perf_counter()
        try:
            provider, model_profile = self.provider_registry.resolve(
                model,
                capability="subject_replace",
            )
        except VideoGenerationProviderError as exc:
            raise CanvasReplacementTaskError(str(exc)) from exc
        if not shots:
            raise CanvasReplacementTaskError("至少选择一个需要替换的镜头")
        prompt_by_shot = {
            int(item["shot_index"]): str(item["prompt"]).strip()
            for item in prompts
            if isinstance(item, dict) and isinstance(item.get("shot_index"), int) and str(item.get("prompt") or "").strip()
        }
        if any(int(shot["index"]) not in prompt_by_shot for shot in shots):
            raise CanvasReplacementTaskError("所选镜头缺少已审核的替换提示词")
        if any(int(item.get("input_revision") or 0) != 5 for item in prompts):
            raise CanvasReplacementTaskError("视频编辑指令使用的是旧结构，请重新生成视频编辑指令后再提交")

        logger.info(
            "canvas.video.replacement.submit.start project_id=%s provider=%s model=%s "
            "target_asset_ids=%s shot_indices=%s prompt_count=%d",
            project_id,
            provider.key,
            model,
            target_asset_ids,
            [int(shot["index"]) for shot in shots],
            len(prompts),
        )
        for prompt_item in sorted(prompts, key=lambda item: int(item["shot_index"])):
            logger.info(
                "canvas.video.replacement.prompt project_id=%s provider=%s model=%s shot_index=%02d "
                "input_revision=%s status=%s\n%s",
                project_id,
                provider.key,
                model,
                int(prompt_item["shot_index"]),
                prompt_item.get("input_revision"),
                prompt_item.get("status"),
                str(prompt_item.get("prompt") or ""),
            )

        target_upload_started = time.perf_counter()
        target_urls = await asyncio.gather(*[
            self._upload_asset(project_id, asset_id, expected_prefix="image/")
            for asset_id in target_asset_ids
        ])
        logger.info(
            "canvas.video.replacement.targets.uploaded project_id=%s provider=%s "
            "target_asset_ids=%s target_urls=%s elapsed_seconds=%.3f",
            project_id,
            provider.key,
            target_asset_ids,
            [self._safe_url(url) for url in target_urls],
            time.perf_counter() - target_upload_started,
        )
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SUBMISSIONS)

        async def submit_shot(shot: dict[str, Any]) -> dict[str, Any]:
            shot_index = int(shot["index"])
            async with semaphore:
                try:
                    return await self._submit_one(
                        project_id,
                        provider=provider,
                        model=model_profile,
                        shot=shot,
                        prompt=prompt_by_shot[shot_index],
                        target_urls=target_urls,
                    )
                except (CanvasReplacementTaskError, VideoGenerationProviderError) as exc:
                    logger.error(
                        "canvas.video.replacement.shot.failed project_id=%s provider=%s model=%s "
                        "shot_index=%02d error=%s",
                        project_id,
                        provider.key,
                        model,
                        shot_index,
                        exc,
                    )
                    return self._result_payload(
                        shot,
                        model=model_profile.id,
                        status="failed",
                        error=str(exc),
                    )

        results = await asyncio.gather(*[
            submit_shot(shot)
            for shot in sorted(shots, key=lambda item: int(item["index"]))
        ])
        logger.info(
            "canvas.video.replacement.submit.done project_id=%s provider=%s model=%s results=%s "
            "elapsed_seconds=%.3f",
            project_id,
            provider.key,
            model,
            [
                {
                    "shot_index": result.get("shot_index"),
                    "status": result.get("status"),
                    "provider_task_id": result.get("provider_task_id"),
                    "error": result.get("error"),
                }
                for result in results
            ],
            time.perf_counter() - submit_started,
        )
        return results

    async def refresh(
        self,
        project_id: str,
        *,
        model: str,
        provider_task_id: str,
        shot: dict[str, Any],
        existing_result_asset_id: str = "",
    ) -> dict[str, Any]:
        if existing_result_asset_id:
            try:
                asset, _ = self.project_service.get_asset_file(project_id, existing_result_asset_id)
            except CanvasAssetNotFoundError:
                pass
            else:
                return self._result_payload(
                    shot,
                    model=model,
                    status="succeeded",
                    provider_task_id=provider_task_id,
                    result_asset=asset,
                )
        if not provider_task_id:
            raise CanvasReplacementTaskError("缺少视频供应商任务标识")
        try:
            selected_provider, model_profile = self.provider_registry.resolve(
                model,
                capability="subject_replace",
            )
            snapshot = await selected_provider.refresh(
                model_profile,
                provider_task_id,
                VideoProviderContext(
                    project_id=project_id,
                    shot_index=int(shot["index"]),
                    source_asset_id=str(shot.get("asset_id") or ""),
                    source_asset_name=str(shot.get("asset_name") or ""),
                ),
            )
        except VideoGenerationProviderError as exc:
            raise CanvasReplacementTaskError(str(exc)) from exc
        result_asset = None
        if snapshot.status == "succeeded":
            if not snapshot.result_url:
                raise CanvasReplacementTaskError("视频任务已完成，但没有返回可下载的视频地址")
            result_asset = await self._download_result(project_id, shot, snapshot.result_url)
        return self._result_payload(
            shot,
            model=snapshot.model,
            status=snapshot.status,
            provider_task_id=snapshot.provider_task_id,
            result_asset=result_asset,
            error=snapshot.error,
        )

    async def _submit_one(
        self,
        project_id: str,
        *,
        provider: VideoGenerationProvider,
        model: VideoModelProfile,
        shot: dict[str, Any],
        prompt: str,
        target_urls: list[str],
    ) -> dict[str, Any]:
        shot_index = int(shot["index"])
        source_upload_started = time.perf_counter()
        source_url, duration, ratio = await self._upload_shot_video(
            project_id,
            shot,
            min_duration_seconds=model.min_duration_seconds,
            max_duration_seconds=model.max_duration_seconds,
        )
        source_upload_elapsed = time.perf_counter() - source_upload_started
        snapshot = await provider.submit(
            model,
            VideoEditRequest(
                prompt=prompt,
                source_video_url=source_url,
                reference_image_urls=tuple(target_urls),
                duration_seconds=duration,
                aspect_ratio=ratio,
            ),
            VideoProviderContext(
                project_id=project_id,
                shot_index=shot_index,
                source_asset_id=str(shot.get("asset_id") or ""),
                source_asset_name=str(shot.get("asset_name") or ""),
                source_upload_seconds=source_upload_elapsed,
            ),
        )
        result_asset = None
        if snapshot.status == "succeeded" and snapshot.result_url:
            result_asset = await self._download_result(project_id, shot, snapshot.result_url)
        return self._result_payload(
            shot,
            model=snapshot.model,
            status=snapshot.status,
            provider_task_id=snapshot.provider_task_id,
            result_asset=result_asset,
            error=snapshot.error,
        )

    @staticmethod
    def _safe_url(url: str) -> str:
        """Keep the object location visible in logs without leaking its signature."""
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))

    async def _upload_shot_video(
        self,
        project_id: str,
        shot: dict[str, Any],
        *,
        min_duration_seconds: float,
        max_duration_seconds: float,
    ) -> tuple[str, int, str]:
        asset_id = str(shot["asset_id"])
        try:
            asset, source_path = self.project_service.get_asset_file(project_id, asset_id)
        except CanvasAssetNotFoundError as exc:
            raise CanvasReplacementTaskError(f"镜头 {int(shot['index']):02d} 的源视频不存在") from exc
        if not str(asset.get("mime_type") or "").startswith("video/"):
            raise CanvasReplacementTaskError(f"镜头 {int(shot['index']):02d} 不是视频素材")
        source_duration = float(shot["duration_seconds"])
        if not min_duration_seconds <= source_duration <= max_duration_seconds:
            raise CanvasReplacementTaskError(
                f"镜头 {int(shot['index']):02d} 时长为 {source_duration:.2f} 秒，不在视频编辑 "
                f"{min_duration_seconds:.0f}–{max_duration_seconds:.0f} 秒范围内；请在原视频节点重新按镜头分段"
            )
        source_url = await self._upload_path(project_id, source_path, "video/mp4")
        # Providers receive whole-second jobs; composition later trims the result
        # back to the exact source segment duration.
        return source_url, math.ceil(source_duration), self._video_ratio(source_path)

    async def _upload_asset(self, project_id: str, asset_id: str, *, expected_prefix: str) -> str:
        try:
            asset, path = self.project_service.get_asset_file(project_id, asset_id)
        except CanvasAssetNotFoundError as exc:
            raise CanvasReplacementTaskError("目标参考图不存在") from exc
        mime_type = str(asset.get("mime_type") or "")
        if not mime_type.startswith(expected_prefix):
            raise CanvasReplacementTaskError(f"素材“{asset['filename']}”不是支持的 {expected_prefix} 素材")
        return await self._upload_path(project_id, path, mime_type)

    async def _upload_path(self, project_id: str, path: Path, mime_type: str) -> str:
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise CanvasReplacementTaskError("本地素材不存在") from exc
        if size <= 0 or size > self.config.max_asset_bytes:
            raise CanvasReplacementTaskError("提交素材为空或超过画布素材大小限制")

        def upload() -> str:
            try:
                with path.open("rb") as source:
                    _, object_key = self.object_storage.upload(
                        project_id, source, size, path.name, mime_type
                    )
                return self.object_storage.presign_download(object_key)
            except VideoAssetPublisherError as exc:
                raise CanvasReplacementTaskError(f"上传视频替换素材失败：{exc}") from exc

        return await asyncio.to_thread(upload)

    async def _download_result(
        self, project_id: str, shot: dict[str, Any], video_url: str
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
                response = await client.get(video_url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CanvasReplacementTaskError(f"下载镜头 {int(shot['index']):02d} 的生成结果失败：{exc}") from exc
        content = response.content
        if not content or len(content) > self.config.max_asset_bytes:
            raise CanvasReplacementTaskError("视频替换结果为空或超过画布素材大小限制")
        return self.project_service.save_asset(
            project_id,
            f"镜头-{int(shot['index']):02d}-替换结果.mp4",
            "video/mp4",
            content,
        )

    @staticmethod
    def _image_references(count: int) -> str:
        if count == 1:
            return "@图片1"
        return f"@图片1 至 @图片{count}"

    @staticmethod
    def _image_reference_range(start: int, count: int) -> str:
        if count == 1:
            return f"@图片{start}"
        return f"@图片{start} 至 @图片{start + count - 1}"

    @staticmethod
    def _video_ratio(source_path: Path) -> str:
        try:
            with av.open(str(source_path)) as container:
                stream = container.streams.video[0]
                width, height = int(stream.width), int(stream.height)
        except (av.error.FFmpegError, IndexError, OSError, ValueError):
            return "adaptive"
        if width <= 0 or height <= 0:
            return "adaptive"
        candidates = {"16:9": 16 / 9, "4:3": 4 / 3, "1:1": 1, "3:4": 3 / 4, "9:16": 9 / 16}
        ratio = width / height
        return min(candidates, key=lambda item: abs(candidates[item] - ratio))

    @staticmethod
    def _result_payload(
        shot: dict[str, Any],
        *,
        model: str,
        status: str,
        provider_task_id: str = "",
        result_asset: dict[str, Any] | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        return {
            "shot_index": int(shot["index"]),
            "source_asset_id": str(shot["asset_id"]),
            "source_asset_name": str(shot["asset_name"]),
            "duration_seconds": float(shot["duration_seconds"]),
            "model": model,
            "provider_task_id": provider_task_id,
            "status": status,
            "result_asset": result_asset,
            "error": error,
        }
