"""Download one allowlisted source video into its shot-detection job folder."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiofiles
import httpx

from backend.app.services.media import MediaResource
from backend.app.services.shot_detection.errors import ShotMediaDownloadError


class VideoDownloader:
    """Download a bounded media resource without exposing arbitrary URLs."""

    def __init__(self, max_media_bytes: int) -> None:
        self.max_media_bytes = max_media_bytes

    async def download(self, resource: MediaResource, destination: Path) -> None:
        temporary_path = destination.with_suffix(".partial")
        timeout = httpx.Timeout(connect=20, read=120, write=30, pool=20)
        downloaded = 0
        try:
            async with httpx.AsyncClient(
                headers=resource.headers,
                follow_redirects=True,
                timeout=timeout,
            ) as client:
                async with client.stream("GET", resource.source_url) as response:
                    response.raise_for_status()
                    content_length = int(response.headers.get("Content-Length", "0"))
                    if content_length > self.max_media_bytes:
                        raise ShotMediaDownloadError("视频文件过大，暂不支持自动分镜")
                    async with aiofiles.open(temporary_path, "wb") as output:
                        async for chunk in response.aiter_bytes(256 * 1024):
                            downloaded += len(chunk)
                            if downloaded > self.max_media_bytes:
                                raise ShotMediaDownloadError(
                                    "视频文件过大，暂不支持自动分镜"
                                )
                            await output.write(chunk)
            if downloaded == 0:
                raise ShotMediaDownloadError("视频文件为空，无法进行分镜识别")
            await asyncio.to_thread(temporary_path.replace, destination)
        except ShotMediaDownloadError:
            raise
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise ShotMediaDownloadError(f"视频下载失败：{exc}") from exc
        finally:
            if temporary_path.exists():
                await asyncio.to_thread(temporary_path.unlink)
