"""Resolve share links and persist their media inside a canvas project."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
import logging
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any, Literal

import av
import httpx

from backend.app.services.douyin.resolver import resolve_share_text
from backend.app.services.media import MediaRegistry, MediaResource
from backend.app.services.platforms import resolve_platform, share_url_from_text
from backend.app.services.session import LoginCookieStore
from backend.app.services.tiktok.resolver import resolve_share_url as resolve_tiktok_share_url

from .service import CanvasProjectService


logger = logging.getLogger("uvicorn.error")


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
        ffmpeg_binary: str = "ffmpeg",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.project_service = project_service
        self.cookie_store = cookie_store
        self.media_registry = media_registry
        self.max_bytes = max_bytes
        self.ffmpeg_binary = ffmpeg_binary
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
            # The mixed track must come from the downloaded video container.
            # Platform audio URLs commonly point to music-only assets and may
            # omit narration, sound effects, or other sounds heard in the video.
            _ResolvedOutput("audio", "视频混合音频", None),
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
        for output, resource in resolved:
            if output.kind == "audio":
                continue
            if resource is not None:
                unique_resources[self._resource_key(resource)] = resource

        downloaded = await asyncio.gather(
            *(self._download(resource) for resource in unique_resources.values())
        )
        saved_assets: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, Any]] = {}
        embedded_audio_asset: dict[str, Any] | None = None
        for (key, resource), (content, mime_type) in zip(unique_resources.items(), downloaded):
            if resource.kind == "video":
                extracted_audio = await asyncio.to_thread(
                    self._extract_video_audio,
                    content,
                    mime_type,
                )
                content, mime_type = await asyncio.to_thread(
                    self._remove_video_audio,
                    content,
                    mime_type,
                )
                if extracted_audio is not None:
                    audio_content, audio_mime_type = extracted_audio
                    embedded_audio_asset = await asyncio.to_thread(
                        self.project_service.save_asset,
                        project_id,
                        f"{media_id}-video-audio{self._extension(audio_mime_type, 'audio')}",
                        audio_mime_type,
                        audio_content,
                    )
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
            if output.kind == "audio":
                response[output.kind] = {
                    "kind": output.kind,
                    "label": output.label,
                    "available": embedded_audio_asset is not None,
                    "asset": embedded_audio_asset,
                    "message": (
                        "已直接从原视频文件提取完整音轨，包含人声、配乐和音效"
                        if embedded_audio_asset is not None
                        else "原视频文件不包含可提取的音轨"
                    ),
                }
                if embedded_audio_asset is None and resolved[0][1] is not None:
                    warnings.append("原视频文件不包含可提取的音轨")
                continue
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
                "message": (
                    "已移除视频音轨并保存到当前画布素材目录"
                    if output.kind == "video"
                    else "已保存到当前画布素材目录"
                ),
            }

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

    def _remove_video_audio(self, content: bytes, mime_type: str) -> tuple[bytes, str]:
        """Remux an extracted video without audio while preserving its video frames."""
        container_mime = mime_type if mime_type in {"video/mp4", "video/webm"} else "video/mp4"
        suffix = ".webm" if container_mime == "video/webm" else ".mp4"
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="canvas-muted-video-") as temp_dir:
            input_path = Path(temp_dir) / f"input{suffix}"
            output_path = Path(temp_dir) / f"output{suffix}"
            input_path.write_bytes(content)
            command = [
                self.ffmpeg_binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(input_path),
                "-map",
                "0:v:0",
                "-c:v",
                "copy",
                "-an",
                "-map_metadata",
                "-1",
            ]
            if container_mime == "video/mp4":
                command.extend(["-movflags", "+faststart"])
            command.extend([str(output_path), "-y"])
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    check=False,
                    timeout=120,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise CanvasMediaExtractionError(f"移除视频音轨失败：{exc}") from exc
            if result.returncode != 0 or not output_path.is_file():
                detail = result.stderr.decode("utf-8", errors="replace").strip()[-800:]
                raise CanvasMediaExtractionError(
                    f"移除视频音轨失败{f'：{detail}' if detail else ''}"
                )
            muted_content = output_path.read_bytes()
        if not muted_content:
            raise CanvasMediaExtractionError("移除视频音轨后文件为空")
        if len(muted_content) > self.max_bytes:
            raise CanvasMediaTooLargeError("无音轨视频超过画布素材大小限制")
        logger.info(
            "canvas.extract_media.video_muted input_bytes=%d output_bytes=%d "
            "mime_type=%s elapsed_seconds=%.3f",
            len(content),
            len(muted_content),
            container_mime,
            time.perf_counter() - started,
        )
        return muted_content, container_mime

    def _extract_video_audio(
        self,
        content: bytes,
        mime_type: str,
    ) -> tuple[bytes, str] | None:
        """Extract the audio stream embedded in the exact downloaded video."""
        try:
            with av.open(BytesIO(content)) as container:
                has_audio = any(stream.type == "audio" for stream in container.streams)
        except (av.error.FFmpegError, OSError, ValueError) as exc:
            raise CanvasMediaExtractionError(f"检查原视频音轨失败：{exc}") from exc
        if not has_audio:
            return None

        container_mime = mime_type if mime_type in {"video/mp4", "video/webm"} else "video/mp4"
        suffix = ".webm" if container_mime == "video/webm" else ".mp4"
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="canvas-video-audio-") as temp_dir:
            input_path = Path(temp_dir) / f"input{suffix}"
            output_path = Path(temp_dir) / "audio.m4a"
            input_path.write_bytes(content)
            command = [
                self.ffmpeg_binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(input_path),
                "-map",
                "0:a:0",
                "-vn",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-map_metadata",
                "-1",
                "-movflags",
                "+faststart",
                str(output_path),
                "-y",
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    check=False,
                    timeout=120,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise CanvasMediaExtractionError(f"提取原视频音轨失败：{exc}") from exc
            if result.returncode != 0 or not output_path.is_file():
                detail = result.stderr.decode("utf-8", errors="replace").strip()[-800:]
                raise CanvasMediaExtractionError(
                    f"提取原视频音轨失败{f'：{detail}' if detail else ''}"
                )
            audio_content = output_path.read_bytes()
        if not audio_content:
            raise CanvasMediaExtractionError("从原视频提取的音轨为空")
        if len(audio_content) > self.max_bytes:
            raise CanvasMediaTooLargeError("从原视频提取的音轨超过画布素材大小限制")
        logger.info(
            "canvas.extract_media.video_audio_extracted input_bytes=%d output_bytes=%d "
            "elapsed_seconds=%.3f",
            len(content),
            len(audio_content),
            time.perf_counter() - started,
        )
        return audio_content, "audio/mp4"

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
