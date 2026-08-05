from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from backend.app.core.config import settings


@dataclass(frozen=True)
class MediaResource:
    source_url: str
    headers: dict[str, str]
    kind: str


class MediaRegistry:
    """Short-lived allowlist used by the media proxy."""

    def __init__(self) -> None:
        self._resources: dict[str, tuple[float, list[MediaResource]]] = {}
        self._lock = threading.Lock()

    def add(self, resources: list[MediaResource]) -> str:
        session_id = uuid.uuid4().hex
        with self._lock:
            self._prune_locked()
            self._resources[session_id] = (time.monotonic(), resources)
        return session_id

    def get(self, session_id: str, index: int) -> MediaResource | None:
        with self._lock:
            self._prune_locked()
            entry = self._resources.get(session_id)
            if entry is None:
                return None
            _, resources = entry
            if index < 0 or index >= len(resources):
                return None
            return resources[index]

    def clear(self) -> None:
        with self._lock:
            self._resources.clear()

    def _prune_locked(self) -> None:
        cutoff = time.monotonic() - settings.media_session_ttl_seconds
        expired = [
            key for key, (created, _) in self._resources.items() if created < cutoff
        ]
        for key in expired:
            self._resources.pop(key, None)


CONTENT_TYPE_FALLBACKS = {
    "audio": "audio/mp4",
    "video": "video/mp4",
    "image": "image/jpeg",
}
FORWARDED_RESPONSE_HEADERS = (
    "Content-Length",
    "Content-Range",
    "Accept-Ranges",
    "Last-Modified",
)


async def create_media_response(
    resource: MediaResource,
    byte_range: str | None,
) -> StreamingResponse:
    """Open an upstream stream and keep it alive for the response iterator."""
    request_headers = dict(resource.headers)
    if byte_range:
        request_headers["Range"] = byte_range
    client = httpx.AsyncClient(
        headers=request_headers,
        follow_redirects=True,
        timeout=httpx.Timeout(60),
    )
    try:
        request = client.build_request("GET", resource.source_url)
        response = await client.send(request, stream=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail="媒体加载失败") from exc

    async def chunks() -> AsyncIterator[bytes]:
        try:
            async for chunk in response.aiter_bytes(64 * 1024):
                yield chunk
        except (httpx.HTTPError, asyncio.CancelledError):
            return
        finally:
            await response.aclose()
            await client.aclose()

    content_type = response.headers.get("Content-Type") or CONTENT_TYPE_FALLBACKS.get(
        resource.kind, "application/octet-stream"
    )
    response_headers = {
        header: value
        for header in FORWARDED_RESPONSE_HEADERS
        if (value := response.headers.get(header))
    }
    response_headers["Cache-Control"] = "private, max-age=300"
    return StreamingResponse(
        chunks(),
        status_code=response.status_code,
        media_type=content_type,
        headers=response_headers,
    )
