"""Volcengine Ark Seedance adapter for the generic video provider contract."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..contracts import (
    VideoEditRequest,
    VideoGenerationProviderError,
    VideoModelProfile,
    VideoProviderContext,
    VideoTaskSnapshot,
)


logger = logging.getLogger("uvicorn.error")
REQUEST_ID_PATTERN = re.compile(r"request\s*id\s*:\s*([a-z0-9]+)", re.IGNORECASE)


@dataclass(frozen=True)
class SeedanceProviderConfig:
    api_key: str
    api_url: str
    log_presigned_urls: bool = False


class SeedanceVideoProvider:
    key = "seedance"
    models = (
        VideoModelProfile(
            id="doubao-seedance-2-0-mini-260615",
            provider=key,
            remote_model="doubao-seedance-2-0-mini-260615",
            label="Seedance 2.0 Mini",
            capabilities=frozenset({"subject_replace", "video_edit"}),
        ),
        VideoModelProfile(
            id="doubao-seedance-2-0-260128",
            provider=key,
            remote_model="doubao-seedance-2-0-260128",
            label="Seedance 2.0",
            capabilities=frozenset({"subject_replace", "video_edit"}),
        ),
        VideoModelProfile(
            id="doubao-seedance-2-0-fast-260128",
            provider=key,
            remote_model="doubao-seedance-2-0-fast-260128",
            label="Seedance 2.0 Fast",
            capabilities=frozenset({"subject_replace", "video_edit"}),
        ),
    )

    def __init__(self, config: SeedanceProviderConfig) -> None:
        self.config = config

    async def submit(
        self,
        model: VideoModelProfile,
        request: VideoEditRequest,
        context: VideoProviderContext,
    ) -> VideoTaskSnapshot:
        self._require_configuration()
        payload = {
            "model": model.remote_model,
            "content": self.request_content(
                request.prompt,
                request.source_video_url,
                list(request.reference_image_urls),
            ),
            "generate_audio": request.generate_audio,
            "watermark": request.watermark,
            "duration": request.duration_seconds,
            "ratio": request.aspect_ratio,
        }
        safe_payload = {
            **payload,
            "content": self.request_content(
                request.prompt,
                self._log_url(request.source_video_url),
                [self._log_url(url) for url in request.reference_image_urls],
            ),
        }
        logger.info(
            "canvas.video.provider.request provider=%s project_id=%s shot_index=%02d "
            "source_asset_id=%s source_asset_name=%r source_upload_seconds=%.3f payload=%r",
            self.key,
            context.project_id,
            context.shot_index,
            context.source_asset_id,
            context.source_asset_name,
            context.source_upload_seconds,
            safe_payload,
        )
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    self.config.api_url,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            logger.exception(
                "canvas.video.provider.network_error provider=%s project_id=%s "
                "shot_index=%02d elapsed_seconds=%.3f",
                self.key,
                context.project_id,
                context.shot_index,
                time.perf_counter() - started,
            )
            raise VideoGenerationProviderError(
                f"镜头 {context.shot_index:02d} 提交失败：{exc}"
            ) from exc
        return self._snapshot_from_response(
            response,
            model,
            context,
            elapsed_seconds=time.perf_counter() - started,
        )

    async def refresh(
        self,
        model: VideoModelProfile,
        provider_task_id: str,
        context: VideoProviderContext,
    ) -> VideoTaskSnapshot:
        self._require_configuration()
        if not provider_task_id:
            raise VideoGenerationProviderError("缺少视频供应商任务标识")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.config.api_url.rstrip('/')}/{provider_task_id}",
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                )
        except httpx.HTTPError as exc:
            raise VideoGenerationProviderError(f"查询视频任务失败：{exc}") from exc
        return self._snapshot_from_response(
            response,
            model,
            context,
            fallback_task_id=provider_task_id,
        )

    def _snapshot_from_response(
        self,
        response: httpx.Response,
        model: VideoModelProfile,
        context: VideoProviderContext,
        *,
        elapsed_seconds: float = 0,
        fallback_task_id: str = "",
    ) -> VideoTaskSnapshot:
        body = self._response_json(response)
        error_body = body.get("error") if isinstance(body, dict) else None
        error_body = error_body if isinstance(error_body, dict) else {}
        failure = self._provider_failure(body)
        response_task_id = body.get("id") if isinstance(body, dict) else None
        provider_task_id = response_task_id or fallback_task_id
        request_id = self._request_id(body, failure)
        logger.info(
            "canvas.video.provider.response provider=%s project_id=%s shot_index=%02d "
            "http_status=%d elapsed_seconds=%.3f provider_task_id=%r provider_status=%r "
            "error_code=%r error_message=%r request_id=%r",
            self.key,
            context.project_id,
            context.shot_index,
            response.status_code,
            elapsed_seconds,
            response_task_id or fallback_task_id,
            body.get("status") if isinstance(body, dict) else None,
            error_body.get("code"),
            failure if response.is_error or self._task_status(body) == "failed" else "",
            request_id,
        )
        if response.is_error:
            raise VideoGenerationProviderError(
                f"Seedance 视频接口返回 {response.status_code}：{failure}"
            )
        if not isinstance(provider_task_id, str) or not provider_task_id:
            raise VideoGenerationProviderError("Seedance 视频接口没有返回任务标识")
        status = self._task_status(body)
        return VideoTaskSnapshot(
            provider=self.key,
            model=model.id,
            provider_task_id=provider_task_id,
            status=status,
            result_url=self._video_url(body),
            error=failure if status == "failed" else "",
            error_code=str(error_body.get("code") or ""),
            request_id=request_id,
        )

    def _require_configuration(self) -> None:
        if not self.config.api_key:
            raise VideoGenerationProviderError("未配置 Seedance ARK_API_KEY")
        if not self.config.api_url:
            raise VideoGenerationProviderError("未配置 Seedance API 地址")

    @staticmethod
    def request_content(
        prompt: str,
        source_url: str,
        target_urls: list[str],
    ) -> list[dict[str, Any]]:
        return [
            {"type": "text", "text": prompt},
            {
                "type": "video_url",
                "role": "reference_video",
                "video_url": {"url": source_url},
            },
            *[
                {
                    "type": "image_url",
                    "role": "reference_image",
                    "image_url": {"url": url},
                }
                for url in target_urls
            ],
        ]

    def _log_url(self, url: str) -> str:
        if self.config.log_presigned_urls:
            return url
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))

    @staticmethod
    def _response_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text[:2_000]}

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
        return "视频生成任务失败"

    @staticmethod
    def _request_id(body: Any, failure: str) -> str:
        if not isinstance(body, dict):
            return ""
        error = body.get("error")
        error = error if isinstance(error, dict) else {}
        request_id = (
            body.get("request_id")
            or body.get("requestId")
            or error.get("request_id")
            or error.get("requestId")
        )
        if request_id:
            return str(request_id)
        match = REQUEST_ID_PATTERN.search(failure)
        return match.group(1) if match else ""
