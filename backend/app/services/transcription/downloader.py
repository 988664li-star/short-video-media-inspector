"""Download allowlisted media for a temporary transcription job."""

from __future__ import annotations

from pathlib import Path

import aiofiles
import httpx

from backend.app.services.media import MediaResource
from backend.app.services.transcription.errors import MediaDownloadError


class TranscriptionMediaDownloader:
    """Download a bounded media resource using the resolver-provided headers."""

    def __init__(self, max_media_bytes: int) -> None:
        self.max_media_bytes = max_media_bytes

    async def download(self, resource: MediaResource, destination: Path) -> None:
        timeout = httpx.Timeout(connect=20, read=120, write=30, pool=20)
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
                        raise MediaDownloadError("媒体文件过大，暂不支持自动转写")
                    downloaded = 0
                    async with aiofiles.open(destination, "wb") as output:
                        async for chunk in response.aiter_bytes(256 * 1024):
                            downloaded += len(chunk)
                            if downloaded > self.max_media_bytes:
                                raise MediaDownloadError(
                                    "媒体文件过大，暂不支持自动转写"
                                )
                            await output.write(chunk)
        except MediaDownloadError:
            raise
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise MediaDownloadError(f"音频读取失败：{exc}") from exc
        if not destination.exists() or destination.stat().st_size == 0:
            raise MediaDownloadError("音频文件为空，无法生成文案")
