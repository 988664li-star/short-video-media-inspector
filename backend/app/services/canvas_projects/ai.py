"""AI execution services for runnable canvas nodes."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.app.services.siliconflow import SiliconFlowClient, SiliconFlowError

from .service import CanvasAssetNotFoundError, CanvasProjectService


class CanvasAIError(RuntimeError):
    """A canvas AI node could not complete its requested operation."""


@dataclass(frozen=True)
class CanvasAIConfig:
    image_api_key: str
    image_api_url: str
    image_model: str
    text_model: str


class CanvasAIService:
    """Run text and image nodes, then store generated media in the canvas project."""

    def __init__(
        self,
        project_service: CanvasProjectService,
        text_client: SiliconFlowClient,
        config: CanvasAIConfig,
    ) -> None:
        self.project_service = project_service
        self.text_client = text_client
        self.config = config

    async def generate_text(self, prompt: str, context: str) -> dict[str, str]:
        user_content = prompt
        if context:
            user_content = f"用户要求：\n{prompt}\n\n上游节点提供的参考内容：\n{context}"
        try:
            result, _ = await self.text_client.complete_json(
                system_prompt=(
                    "你是无限画布中的文本创作节点。严格执行用户要求，并结合上游参考内容。"
                    "返回 JSON 对象，且只能包含 content 字段；content 必须是可直接放入文档节点的完整正文。"
                ),
                content=user_content,
                max_tokens=4_096,
                timeout_seconds=120,
                temperature=0.7,
                log_context="canvas.text.generate",
                enable_thinking=False,
            )
        except SiliconFlowError as exc:
            raise CanvasAIError(str(exc)) from exc
        content = result.get("content")
        if not isinstance(content, str) or not content.strip():
            raise CanvasAIError("文本模型没有返回可用内容")
        return {"content": content.strip(), "model": self.config.text_model}

    async def generate_image(
        self,
        project_id: str,
        prompt: str,
        source_url: str,
        source_asset_ids: list[str],
        aspect_ratio: str = "原比例",
    ) -> dict[str, Any]:
        if not self.config.image_api_key:
            raise CanvasAIError("服务端未设置 ARK_API_KEY，无法调用 Seedream 图片模型")
        references = await self._reference_images(project_id, source_url, source_asset_ids)
        provider_payload: dict[str, Any] = {
            "model": self.config.image_model,
            "prompt": prompt,
            "size": self._image_size(aspect_ratio),
            "response_format": "b64_json",
            "watermark": False,
        }
        if references:
            provider_payload["image"] = references
        try:
            async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
                response = await client.post(
                    self.config.image_api_url,
                    headers={"Authorization": f"Bearer {self.config.image_api_key}"},
                    json=provider_payload,
                )
        except httpx.HTTPError as exc:
            raise CanvasAIError(f"Seedream 图片请求失败：{exc}") from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise CanvasAIError(f"Seedream 返回了无法解析的响应（HTTP {response.status_code}）") from exc
        if response.is_error:
            raise CanvasAIError(self._provider_error(body, response.status_code))
        image_bytes, mime_type = await self._result_image(body)
        extension = ".png" if mime_type == "image/png" else ".jpg"
        asset = self.project_service.save_asset(
            project_id,
            f"AI生成-{int(time.time())}{extension}",
            mime_type,
            image_bytes,
        )
        return {"asset": asset, "model": self.config.image_model}

    @staticmethod
    def _image_size(aspect_ratio: str) -> str:
        return {
            "9:16": "1536x2688",
            "16:9": "2688x1536",
            "1:1": "2048x2048",
            "原比例": "2048x2048",
        }.get(aspect_ratio, "2048x2048")

    async def _reference_images(
        self,
        project_id: str,
        source_url: str,
        source_asset_ids: list[str],
    ) -> list[str]:
        references: list[str] = []
        if source_url:
            parsed = urlparse(source_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise CanvasAIError("参考图片网址必须是可访问的 HTTP 或 HTTPS 地址")
            references.append(source_url)
        for asset_id in dict.fromkeys(source_asset_ids):
            try:
                asset, path = self.project_service.get_asset_file(project_id, asset_id)
            except CanvasAssetNotFoundError as exc:
                raise CanvasAIError(f"参考图片不存在：{asset_id}") from exc
            mime_type = str(asset["mime_type"]).lower()
            if mime_type not in {"image/jpeg", "image/jpg", "image/png", "image/webp"}:
                raise CanvasAIError(f"参考素材不是支持的图片格式：{asset['filename']}")
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            references.append(f"data:{mime_type};base64,{encoded}")
        return references

    async def _result_image(self, body: Any) -> tuple[bytes, str]:
        data = body.get("data") if isinstance(body, dict) else None
        first = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else None
        if not isinstance(first, dict):
            raise CanvasAIError("Seedream 没有返回图片结果")
        encoded = first.get("b64_json")
        if isinstance(encoded, str) and encoded:
            try:
                content = base64.b64decode(encoded, validate=True)
            except (TypeError, ValueError) as exc:
                raise CanvasAIError("Seedream 返回的图片数据无法解码") from exc
            if not content:
                raise CanvasAIError("Seedream 返回了空图片")
            return content, "image/png"
        output_url = first.get("url")
        if isinstance(output_url, str) and output_url.startswith(("http://", "https://")):
            try:
                async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                    response = await client.get(output_url)
                    response.raise_for_status()
            except httpx.HTTPError as exc:
                raise CanvasAIError(f"下载 Seedream 图片结果失败：{exc}") from exc
            mime_type = response.headers.get("content-type", "image/jpeg").split(";", maxsplit=1)[0]
            return response.content, "image/png" if mime_type == "image/png" else "image/jpeg"
        raise CanvasAIError("Seedream 没有返回可保存的图片")

    @staticmethod
    def _provider_error(body: Any, status_code: int) -> str:
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                return f"Seedream 图片接口返回 {status_code}：{error['message']}"
            if isinstance(body.get("message"), str):
                return f"Seedream 图片接口返回 {status_code}：{body['message']}"
        return f"Seedream 图片接口返回 HTTP {status_code}"
