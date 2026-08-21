"""Resolve share links and persist their media inside a canvas project."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Literal

import httpx

from backend.app.services.douyin.resolver import resolve_share_text
from backend.app.services.media import MediaRegistry, MediaResource
from backend.app.services.platforms import resolve_platform, share_url_from_text
from backend.app.services.session import LoginCookieStore
from backend.app.services.tiktok.resolver import resolve_share_url as resolve_tiktok_share_url

from .service import CanvasProjectService


MEDIA_PROXY_PATTERN = re.compile(r"^/api/media/([a-f0-9]{32})/(\d+)$")
PlatformChoice = Literal["auto", "douyin", "tiktok"]


class CanvasMediaExtractionError(RuntimeError):
    """The share link resolved, but its media could not be stored."""


class CanvasMediaTooLargeError(CanvasMediaExtractionError):
    """A resolved media file exceeds the configured canvas limit."""


@dataclass(frozen=True)
class _ResolvedOutput:
    kind: Literal["video", "music", "audio"]
    label: str
    media: dict[str, Any] | None


class CanvasMediaExtractionService:
    """Turn one public share link into durable canvas media assets."""

    def __init__(
        self,
        project_service: CanvasProjectService,
        cookie_store: LoginCookieStore,
        media_registry: MediaRegistry,
        max_bytes: int,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.project_service = project_service
        self.cookie_store = cookie_store
        self.media_registry = media_registry
        self.max_bytes = max_bytes
        self.transport = transport

    async def extract(
        self,
        project_id: str,
        share_text: str,
        platform_choice: PlatformChoice = "auto",
    ) -> dict[str, Any]:
        self.project_service.get_project(project_id)
        share_url = share_url_from_text(share_text)
        platform = resolve_platform(share_url, platform_choice)
        payload = (
            await resolve_tiktok_share_url(share_url, self.media_registry)
            if platform == "tiktok"
            else await resolve_share_text(
                share_text,
                self.cookie_store,
                self.media_registry,
            )
        )

        outputs = [
            _ResolvedOutput("video", "原视频", self._mapping(payload.get("video"))),
            _ResolvedOutput(
                "music",
                "作品配乐",
                self._mapping(self._mapping(payload.get("music")).get("audio")),
            ),
            _ResolvedOutput("audio", "视频混合音频", self._mapping(payload.get("audio"))),
        ]
        materialized, extraction_warnings = await self._materialize(
            project_id,
            str(payload.get("aweme_id") or "media"),
            outputs,
        )
        warnings = [
            str(item)
            for item in payload.get("warnings") or []
            if isinstance(item, str) and item.strip()
        ]
        warnings.extend(extraction_warnings)
        return {
            "platform": platform,
            "aweme_id": str(payload.get("aweme_id") or ""),
            "description": str(payload.get("description") or ""),
            "author": self._mapping(payload.get("author")),
            "duration_ms": payload.get("duration_ms"),
            "outputs": materialized,
            "warnings": list(dict.fromkeys(warnings)),
        }

    async def _materialize(
        self,
        project_id: str,
        media_id: str,
        outputs: list[_ResolvedOutput],
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        resolved: list[tuple[_ResolvedOutput, MediaResource | None]] = [
            (output, self._resource(output.media)) for output in outputs
        ]
        unique_resources: dict[tuple[str, tuple[tuple[str, str], ...]], MediaResource] = {}
        for _, resource in resolved:
            if resource is not None:
                unique_resources[self._resource_key(resource)] = resource

        downloaded = await asyncio.gather(
            *(self._download(resource) for resource in unique_resources.values())
        )
        saved_assets: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, Any]] = {}
        for (key, resource), (content, mime_type) in zip(unique_resources.items(), downloaded):
            filename = f"{media_id}-{resource.kind}{self._extension(mime_type, resource.kind)}"
            saved_assets[key] = await asyncio.to_thread(
                self.project_service.save_asset,
                project_id,
                filename,
                mime_type,
                content,
            )

        response: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for output, resource in resolved:
            if resource is None:
                response[output.kind] = {
                    "kind": output.kind,
                    "label": output.label,
                    "available": False,
                    "asset": None,
                    "message": f"平台没有返回可单独保存的{output.label}",
                }
                continue
            asset = saved_assets[self._resource_key(resource)]
            response[output.kind] = {
                "kind": output.kind,
                "label": output.label,
                "available": True,
                "asset": asset,
                "message": "已保存到当前画布素材目录",
            }

        music_resource = resolved[1][1]
        audio_resource = resolved[2][1]
        if (
            music_resource is not None
            and audio_resource is not None
            and self._resource_key(music_resource) == self._resource_key(audio_resource)
        ):
            message = "平台返回的作品配乐与视频混合音频是同一条音轨，两个节点引用同一本地文件"
            response["music"]["message"] = message
            response["audio"]["message"] = message
            warnings.append(message)
        return response, warnings

    def _resource(self, media: dict[str, Any] | None) -> MediaResource | None:
        if not media:
            return None
        match = MEDIA_PROXY_PATTERN.fullmatch(str(media.get("proxy_url") or ""))
        if match is None:
            return None
        return self.media_registry.get(match.group(1), int(match.group(2)))

    async def _download(self, resource: MediaResource) -> tuple[bytes, str]:
        try:
            async with httpx.AsyncClient(
                headers=resource.headers,
                follow_redirects=True,
                timeout=httpx.Timeout(60),
                transport=self.transport,
            ) as client:
                async with client.stream("GET", resource.source_url) as response:
                    response.raise_for_status()
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes(128 * 1024):
                        total += len(chunk)
                        if total > self.max_bytes:
                            raise CanvasMediaTooLargeError(
                                f"{resource.kind} 文件超过画布素材大小限制"
                            )
                        chunks.append(chunk)
                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
        except CanvasMediaTooLargeError:
            raise
        except httpx.HTTPError as exc:
            raise CanvasMediaExtractionError(f"下载{resource.kind}失败：{exc}") from exc
        fallback = "video/mp4" if resource.kind == "video" else "audio/mp4"
        return b"".join(chunks), content_type or fallback

    @staticmethod
    def _resource_key(resource: MediaResource) -> tuple[str, tuple[tuple[str, str], ...]]:
        return resource.source_url, tuple(sorted(resource.headers.items()))

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _extension(mime_type: str, kind: str) -> str:
        return {
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "audio/mpeg": ".mp3",
            "audio/mp4": ".m4a",
            "audio/aac": ".aac",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/ogg": ".ogg",
        }.get(mime_type, ".mp4" if kind == "video" else ".m4a")
