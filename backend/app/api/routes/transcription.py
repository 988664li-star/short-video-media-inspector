from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_media_registry, get_transcription_service
from backend.app.schemas.requests import TranscriptionRequest
from backend.app.services.media import MediaRegistry
from backend.app.services.transcription import (
    MediaDownloadError,
    ModelUnavailableError,
    TranscriptionService,
)


router = APIRouter()
MEDIA_PROXY_PATTERN = re.compile(r"^/api/media/([a-f0-9]{32})/(\d+)$")


@router.post("/transcription")
async def create_transcription(
    request: TranscriptionRequest,
    media_registry: Annotated[MediaRegistry, Depends(get_media_registry)],
    service: Annotated[TranscriptionService, Depends(get_transcription_service)],
) -> dict[str, Any]:
    match = MEDIA_PROXY_PATTERN.fullmatch(request.media_url)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="媒体地址格式不正确，请重新解析分享链接",
        )

    resource = media_registry.get(match.group(1), int(match.group(2)))
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="媒体地址已过期，请重新解析分享链接",
        )
    if resource.kind not in {"audio", "video"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前媒体不包含可转写的声音",
        )

    try:
        return await service.transcribe(request.aweme_id, resource, request.context)
    except MediaDownloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ModelUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
