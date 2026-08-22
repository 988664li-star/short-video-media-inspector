"""Xiaoyunque immersive-video adapter for the generic video provider contract."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from pathlib import PurePosixPath
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..contracts import (
    VideoEditRequest,
    VideoGenerationProviderError,
    VideoModelProfile,
    VideoProviderContext,
    VideoTaskSnapshot,
)


logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class XiaoyunqueProviderConfig:
    api_key: str
    api_base_url: str = "https://xyq.jianying.com/api/biz/v1"


class XiaoyunqueVideoProvider:
    key = "xiaoyunque"
    default_resolution = "720p"
    models = (
        VideoModelProfile(
            id="xiaoyunque-seedance-2-5",
            provider=key,
            remote_model="Seedance_2.5",
            label="小云雀 · Seedance 2.5",
            capabilities=frozenset({"subject_replace", "video_edit"}),
        ),
        VideoModelProfile(
            id="xiaoyunque-seedance-2-0-mini",
            provider=key,
            remote_model="Seedance_2.0_mini",
            label="小云雀 · Seedance 2.0 Mini",
            capabilities=frozenset({"subject_replace", "video_edit"}),
        ),
        VideoModelProfile(
            id="xiaoyunque-seedance-2-0-fast",
            provider=key,
            remote_model="seedance2.0_fast_vision",
            label="小云雀 · Seedance 2.0 Fast",
            capabilities=frozenset({"subject_replace", "video_edit"}),
        ),
        VideoModelProfile(
            id="xiaoyunque-seedance-2-0",
            provider=key,
            remote_model="seedance2.0_vision",
            label="小云雀 · Seedance 2.0",
            capabilities=frozenset({"subject_replace", "video_edit"}),
        ),
        VideoModelProfile(
            id="xiaoyunque-seedance-2-0-mini-lite",
            provider=key,
            remote_model="Seedance_2.0_mini_lite",
            label="小云雀 · Seedance 2.0 Mini Lite",
            capabilities=frozenset({"subject_replace", "video_edit"}),
        ),
    )

    def __init__(
        self,
        config: XiaoyunqueProviderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport

    async def submit(
        self,
        model: VideoModelProfile,
        request: VideoEditRequest,
        context: VideoProviderContext,
    ) -> VideoTaskSnapshot:
        self._require_configuration()
        started = time.perf_counter()
        source_asset_id, reference_asset_ids = await asyncio.gather(
            self._upload_url(
                request.source_video_url,
                fallback_name=context.source_asset_name or f"shot-{context.shot_index:02d}.mp4",
                fallback_content_type="video/mp4",
            ),
            self._upload_references(request.reference_image_urls),
        )
        payload = {
            "message": request.prompt,
            "agent_name": "pippit_video_part_agent",
            "asset_ids": [source_asset_id, *reference_asset_ids],
            "video_part_tool_param": {
                "ratio": self._ratio(request.aspect_ratio),
                "prompt": request.prompt,
                "model": model.remote_model,
                "duration_sec": request.duration_seconds,
                # Although the public table currently marks this field as optional,
                # the production endpoint rejects requests that omit it. 720p is
                # supported across the Xiaoyunque model catalog; 1080p is not.
                "resolution": self.default_resolution,
                "images": [
                    {"pippit_asset_id": asset_id}
                    for asset_id in reference_asset_ids
                ],
                "videos": [{"pippit_asset_id": source_asset_id}],
            },
        }
        logger.info(
            "canvas.video.provider.request provider=%s project_id=%s shot_index=%02d "
            "source_asset_id=%s source_asset_name=%r model=%s duration=%d ratio=%s "
            "resolution=%s reference_asset_count=%d",
            self.key,
            context.project_id,
            context.shot_index,
            context.source_asset_id,
            context.source_asset_name,
            model.id,
            request.duration_seconds,
            self._ratio(request.aspect_ratio),
            self.default_resolution,
            len(reference_asset_ids),
        )
        body = await self._post_json("/skill/submit_run", payload, timeout_seconds=90)
        data = self._mapping(body.get("data"))
        run = self._mapping(data.get("run"))
        thread_id = str(run.get("thread_id") or "")
        run_id = str(run.get("run_id") or "")
        if not thread_id or not run_id:
            raise self._provider_error(body, "小云雀提交成功但没有返回 thread_id/run_id")
        status = self._status(run.get("state"))
        task_id = self._task_id(thread_id, run_id)
        logger.info(
            "canvas.video.provider.response provider=%s project_id=%s shot_index=%02d "
            "elapsed_seconds=%.3f provider_task_id=%r provider_status=%s log_id=%r",
            self.key,
            context.project_id,
            context.shot_index,
            time.perf_counter() - started,
            task_id,
            status,
            body.get("log_id"),
        )
        return VideoTaskSnapshot(
            provider=self.key,
            model=model.id,
            provider_task_id=task_id,
            status=status,
            error=str(body.get("errmsg") or "") if status == "failed" else "",
            request_id=str(body.get("log_id") or ""),
        )

    async def refresh(
        self,
        model: VideoModelProfile,
        provider_task_id: str,
        context: VideoProviderContext,
    ) -> VideoTaskSnapshot:
        self._require_configuration()
        thread_id, run_id = self._parse_task_id(provider_task_id)
        body = await self._post_json(
            "/agent/query_generate_video_result",
            {"thread_id": thread_id, "run_id": run_id},
            timeout_seconds=45,
        )
        data = self._mapping(body.get("data"))
        status = self._status(data.get("run_state"))
        video_urls = data.get("video_urls")
        result_url = next((
            str(url)
            for url in video_urls
            if isinstance(url, str) and url.startswith(("https://", "http://"))
        ), "") if isinstance(video_urls, list) else ""
        fail_reason = self._mapping(data.get("fail_reason"))
        error = str(fail_reason.get("message") or body.get("errmsg") or "")
        error_code = str(fail_reason.get("code") or "")
        logger.info(
            "canvas.video.provider.refresh provider=%s project_id=%s shot_index=%02d "
            "provider_task_id=%r provider_status=%s result_ready=%s error_code=%r log_id=%r",
            self.key,
            context.project_id,
            context.shot_index,
            provider_task_id,
            status,
            bool(result_url),
            error_code,
            body.get("log_id"),
        )
        return VideoTaskSnapshot(
            provider=self.key,
            model=model.id,
            provider_task_id=provider_task_id,
            status=status,
            result_url=result_url,
            error=error if status == "failed" else "",
            error_code=error_code,
            request_id=str(body.get("log_id") or ""),
        )

    async def _upload_references(self, urls: tuple[str, ...]) -> list[str]:
        return list(await asyncio.gather(*[
            self._upload_url(
                url,
                fallback_name=f"reference-{index}.png",
                fallback_content_type="image/png",
            )
            for index, url in enumerate(urls, start=1)
        ]))

    async def _upload_url(
        self,
        url: str,
        *,
        fallback_name: str,
        fallback_content_type: str,
    ) -> str:
        try:
            async with self._client(timeout_seconds=180, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content
                if not content:
                    raise VideoGenerationProviderError("待上传的小云雀素材为空")
                path_name = PurePosixPath(urlsplit(url).path).name
                filename = path_name or fallback_name
                content_type = response.headers.get("content-type", "").split(";", 1)[0]
                upload = await client.post(
                    self._url("/skill/upload_file"),
                    headers=self._headers(json_content=False),
                    files={"file": (filename, content, content_type or fallback_content_type)},
                )
                upload.raise_for_status()
                body = upload.json()
        except VideoGenerationProviderError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise VideoGenerationProviderError(
                f"上传素材到小云雀失败（{type(exc).__name__}）：{str(exc) or '网络连接中断'}"
            ) from exc
        self._require_success(body)
        asset_id = str(self._mapping(body.get("data")).get("pippit_asset_id") or "")
        if not asset_id:
            raise self._provider_error(body, "小云雀文件上传接口没有返回素材 ID")
        return asset_id

    async def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        try:
            async with self._client(timeout_seconds=timeout_seconds) as client:
                response = await client.post(
                    self._url(path),
                    headers=self._headers(json_content=True),
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VideoGenerationProviderError(
                f"小云雀接口请求失败（{type(exc).__name__}）：{str(exc) or '网络连接中断'}"
            ) from exc
        if not isinstance(body, dict):
            raise VideoGenerationProviderError("小云雀接口没有返回 JSON 对象")
        self._require_success(body)
        return body

    def _client(
        self,
        *,
        timeout_seconds: float,
        follow_redirects: bool = False,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(connect=20, read=timeout_seconds, write=180, pool=20),
            follow_redirects=follow_redirects,
            transport=self.transport,
        )

    def _headers(self, *, json_content: bool) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Accept": "application/json",
        }
        if json_content:
            headers["Content-Type"] = "application/json"
        return headers

    def _url(self, path: str) -> str:
        return f"{self.config.api_base_url.rstrip('/')}{path}"

    def _require_configuration(self) -> None:
        if not self.config.api_key:
            raise VideoGenerationProviderError("未配置小云雀 XIAOYUNQUE_API_KEY")
        if not self.config.api_base_url:
            raise VideoGenerationProviderError("未配置小云雀 API 地址")

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @classmethod
    def _require_success(cls, body: Any) -> None:
        if not isinstance(body, dict):
            raise VideoGenerationProviderError("小云雀接口没有返回 JSON 对象")
        if str(body.get("ret")) != "0":
            raise cls._provider_error(body, "小云雀接口调用失败")

    @staticmethod
    def _provider_error(body: dict[str, Any], fallback: str) -> VideoGenerationProviderError:
        message = str(body.get("errmsg") or fallback)
        log_id = str(body.get("log_id") or "")
        suffix = f"；log_id={log_id}" if log_id else ""
        return VideoGenerationProviderError(f"{message}{suffix}")

    @staticmethod
    def _status(value: Any) -> str:
        state = str(value or "1")
        if state == "3":
            return "succeeded"
        if state in {"4", "5"}:
            return "failed"
        if state == "2":
            return "running"
        return "queued"

    @staticmethod
    def _ratio(value: str) -> str:
        return value if value in {"16:9", "9:16", "4:3", "3:4", "1:1"} else "9:16"

    @staticmethod
    def _task_id(thread_id: str, run_id: str) -> str:
        return f"{thread_id}::{run_id}"

    @staticmethod
    def _parse_task_id(value: str) -> tuple[str, str]:
        thread_id, separator, run_id = value.partition("::")
        if not separator or not thread_id or not run_id:
            raise VideoGenerationProviderError("小云雀任务标识格式不正确")
        return thread_id, run_id
