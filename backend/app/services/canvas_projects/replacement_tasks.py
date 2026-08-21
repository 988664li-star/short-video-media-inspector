"""Independent, per-shot Seedance replacement tasks for the creative canvas."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import av
import httpx

from backend.app.services.seedance.object_storage import ObjectStorageError, SeedanceObjectStorage

from .generation import MAX_SEEDANCE_VIDEO_SECONDS, MIN_SEEDANCE_VIDEO_SECONDS
from .prompts import CanvasPromptTemplateError, CanvasPromptTemplates
from .service import CanvasAssetNotFoundError, CanvasProjectService


SEEDANCE_MODELS = {
    "doubao-seedance-2-0-mini-260615",
    "doubao-seedance-2-0-260128",
    "doubao-seedance-2-0-fast-260128",
}
MAX_CONCURRENT_SUBMISSIONS = 3


class CanvasReplacementTaskError(RuntimeError):
    """A per-shot canvas replacement task could not be prepared or submitted."""


@dataclass(frozen=True)
class CanvasReplacementVideoConfig:
    api_key: str
    api_url: str
    max_asset_bytes: int


class CanvasReplacementTaskService:
    """Render, submit and refresh explicit per-shot video replacement tasks.

    This service is intentionally independent from the older continuous-segment
    Seedance workspace. A canvas task always has one contiguous source video
    edit segment and one or more target reference images.
    """

    def __init__(
        self,
        project_service: CanvasProjectService,
        object_storage: SeedanceObjectStorage,
        config: CanvasReplacementVideoConfig,
        prompt_templates: CanvasPromptTemplates | None = None,
    ) -> None:
        self.project_service = project_service
        self.object_storage = object_storage
        self.config = config
        self.prompt_templates = prompt_templates

    def build_prompts(
        self,
        *,
        source_object_name: str,
        source_object_description: str,
        target_description: str,
        target_asset_ids: list[str],
        shots: list[dict[str, Any]],
        actions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not target_asset_ids:
            raise CanvasReplacementTaskError("请先连接至少一张目标对象参考图")
        try:
            template = self.prompt_templates or CanvasPromptTemplates.load()
        except CanvasPromptTemplateError as exc:
            raise CanvasReplacementTaskError(str(exc)) from exc
        action_by_shot = {
            int(item["shot_index"]): str(item["description"])
            for item in actions
            if isinstance(item, dict) and isinstance(item.get("shot_index"), int)
        }
        image_references = self._image_references(len(target_asset_ids))
        prompts: list[dict[str, Any]] = []
        for shot in sorted(shots, key=lambda item: int(item["index"])):
            shot_index = int(shot["index"])
            action = action_by_shot.get(
                shot_index,
                f"{source_object_name} 出现在当前连续片段中，保持原有位置、动作与遮挡关系。",
            )
            prompts.append({
                "shot_index": shot_index,
                "prompt": template.render_shot_replacement_video(
                    source_object_name=source_object_name,
                    source_object_description=source_object_description,
                    target_description=target_description,
                    target_image_references=image_references,
                    shot_action=action,
                ),
                "input_revision": 3,
                "status": "ready",
            })
        return prompts

    async def submit(
        self,
        project_id: str,
        *,
        model: str,
        target_asset_ids: list[str],
        shots: list[dict[str, Any]],
        prompts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not self.config.api_key:
            raise CanvasReplacementTaskError("未配置 ARK_API_KEY，不能提交逐镜头视频替换任务")
        if model not in SEEDANCE_MODELS:
            raise CanvasReplacementTaskError("不支持的逐镜头替换模型")
        if not shots:
            raise CanvasReplacementTaskError("至少选择一个需要替换的镜头")
        prompt_by_shot = {
            int(item["shot_index"]): str(item["prompt"]).strip()
            for item in prompts
            if isinstance(item, dict) and isinstance(item.get("shot_index"), int) and str(item.get("prompt") or "").strip()
        }
        if any(int(shot["index"]) not in prompt_by_shot for shot in shots):
            raise CanvasReplacementTaskError("所选镜头缺少已审核的替换提示词")
        if any(int(item.get("input_revision") or 0) != 3 for item in prompts):
            raise CanvasReplacementTaskError("视频编辑指令使用的是旧结构，请重新生成视频编辑指令后再提交")

        target_urls = await asyncio.gather(*[
            self._upload_asset(project_id, asset_id, expected_prefix="image/")
            for asset_id in dict.fromkeys(target_asset_ids)
        ])
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SUBMISSIONS)

        async def submit_shot(shot: dict[str, Any]) -> dict[str, Any]:
            shot_index = int(shot["index"])
            async with semaphore:
                try:
                    return await self._submit_one(
                        project_id,
                        model=model,
                        shot=shot,
                        prompt=prompt_by_shot[shot_index],
                        target_urls=target_urls,
                    )
                except CanvasReplacementTaskError as exc:
                    return self._result_payload(shot, status="failed", error=str(exc))

        return await asyncio.gather(*[
            submit_shot(shot)
            for shot in sorted(shots, key=lambda item: int(item["index"]))
        ])

    async def refresh(
        self,
        project_id: str,
        *,
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
                    status="succeeded",
                    provider_task_id=provider_task_id,
                    result_asset=asset,
                )
        if not self.config.api_key:
            raise CanvasReplacementTaskError("未配置 ARK_API_KEY，不能刷新视频替换任务")
        if not provider_task_id:
            raise CanvasReplacementTaskError("缺少方舟视频任务标识")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.config.api_url.rstrip('/')}/{provider_task_id}",
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                )
        except httpx.HTTPError as exc:
            raise CanvasReplacementTaskError(f"查询视频替换任务失败：{exc}") from exc
        body = self._response_json(response)
        if response.is_error:
            raise CanvasReplacementTaskError(self._provider_error(body, response.status_code))
        status = self._task_status(body)
        result_asset = None
        if status == "succeeded":
            video_url = self._video_url(body)
            if not video_url:
                raise CanvasReplacementTaskError("视频任务已完成，但没有返回可下载的视频地址")
            result_asset = await self._download_result(project_id, shot, video_url)
        return self._result_payload(
            shot,
            status=status,
            provider_task_id=provider_task_id,
            result_asset=result_asset,
            error=self._provider_failure(body) if status == "failed" else "",
        )

    async def _submit_one(
        self,
        project_id: str,
        *,
        model: str,
        shot: dict[str, Any],
        prompt: str,
        target_urls: list[str],
    ) -> dict[str, Any]:
        source_url, duration, ratio = await self._upload_shot_video(project_id, shot)
        request_payload = {
            "model": model,
            "content": self._request_content(prompt, source_url, target_urls),
            "generate_audio": False,
            "watermark": False,
            "duration": duration,
            "ratio": ratio,
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    self.config.api_url,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    json=request_payload,
                )
        except httpx.HTTPError as exc:
            raise CanvasReplacementTaskError(f"镜头 {int(shot['index']):02d} 提交失败：{exc}") from exc
        body = self._response_json(response)
        if response.is_error:
            raise CanvasReplacementTaskError(self._provider_error(body, response.status_code))
        provider_task_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(provider_task_id, str) or not provider_task_id:
            raise CanvasReplacementTaskError("视频替换接口没有返回任务标识")
        status = self._task_status(body)
        result_asset = None
        if status == "succeeded":
            video_url = self._video_url(body)
            if video_url:
                result_asset = await self._download_result(project_id, shot, video_url)
        return self._result_payload(
            shot,
            status=status,
            provider_task_id=provider_task_id,
            result_asset=result_asset,
            error=self._provider_failure(body) if status == "failed" else "",
        )

    async def _upload_shot_video(
        self, project_id: str, shot: dict[str, Any]
    ) -> tuple[str, int, str]:
        asset_id = str(shot["asset_id"])
        try:
            asset, source_path = self.project_service.get_asset_file(project_id, asset_id)
        except CanvasAssetNotFoundError as exc:
            raise CanvasReplacementTaskError(f"镜头 {int(shot['index']):02d} 的源视频不存在") from exc
        if not str(asset.get("mime_type") or "").startswith("video/"):
            raise CanvasReplacementTaskError(f"镜头 {int(shot['index']):02d} 不是视频素材")
        source_duration = float(shot["duration_seconds"])
        if not MIN_SEEDANCE_VIDEO_SECONDS <= source_duration <= MAX_SEEDANCE_VIDEO_SECONDS:
            raise CanvasReplacementTaskError(
                f"镜头 {int(shot['index']):02d} 时长为 {source_duration:.2f} 秒，不在 Seedance "
                f"{MIN_SEEDANCE_VIDEO_SECONDS:.0f}–{MAX_SEEDANCE_VIDEO_SECONDS:.0f} 秒范围内；请在原视频节点重新按镜头分段"
            )
        source_url = await self._upload_path(project_id, source_path, "video/mp4")
        # Seedance accepts whole seconds. Round upward, then trim the generated
        # result back to the source segment during composition instead of padding
        # the source video with fake frames.
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
            except ObjectStorageError as exc:
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
    def _request_content(
        prompt: str, source_url: str, target_urls: list[str]
    ) -> list[dict[str, Any]]:
        """Keep the multimodal reference order aligned with the prompt template.

        @视频1 is the source edit segment and every image is a target-object
        reference. The compact input package matches the video-edit workflow.
        """
        return [
            {"type": "text", "text": prompt},
            {"type": "video_url", "role": "reference_video", "video_url": {"url": source_url}},
            *[
                {"type": "image_url", "role": "reference_image", "image_url": {"url": url}}
                for url in target_urls
            ],
        ]

    @staticmethod
    def _task_status(body: Any) -> str:
        raw = str(body.get("status") or "queued").lower() if isinstance(body, dict) else "failed"
        if raw in {"succeeded", "success", "completed"}:
            return "succeeded"
        if raw in {"failed", "error", "cancelled", "canceled"}:
            return "failed"
        if raw in {"running", "processing", "in_progress"}:
            return "running"
        return "queued"

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
    def _response_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text[:2_000]}

    @staticmethod
    def _video_url(body: Any) -> str:
        content = body.get("content") if isinstance(body, dict) else None
        url = content.get("video_url") if isinstance(content, dict) else None
        return url if isinstance(url, str) and url.startswith(("https://", "http://")) else ""

    @staticmethod
    def _provider_failure(body: Any) -> str:
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                return error["message"]
            if isinstance(body.get("message"), str):
                return str(body["message"])
        return "视频替换任务失败"

    @classmethod
    def _provider_error(cls, body: Any, status_code: int) -> str:
        return f"Seedance 视频替换接口返回 {status_code}：{cls._provider_failure(body)}"

    @staticmethod
    def _result_payload(
        shot: dict[str, Any],
        *,
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
            "provider_task_id": provider_task_id,
            "status": status,
            "result_asset": result_asset,
            "error": error,
        }
