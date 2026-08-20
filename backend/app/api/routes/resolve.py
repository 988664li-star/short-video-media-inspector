import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import (
    get_cookie_store,
    get_media_registry,
    get_shot_detection_service,
)
from backend.app.schemas.requests import ResolveRequest
from backend.app.services.douyin.resolver import resolve_share_text
from backend.app.services.media import MediaRegistry
from backend.app.services.platforms import resolve_platform, share_url_from_text
from backend.app.services.session import LoginCookieStore
from backend.app.services.shot_detection import ShotDetectionError, ShotDetectionService
from backend.app.services.tiktok.resolver import resolve_share_url as resolve_tiktok_share_url


router = APIRouter()


@router.post("/resolve")
async def resolve_media(
    request: ResolveRequest,
    cookie_store: Annotated[LoginCookieStore, Depends(get_cookie_store)],
    media_registry: Annotated[MediaRegistry, Depends(get_media_registry)],
    shot_detection_service: Annotated[
        ShotDetectionService, Depends(get_shot_detection_service)
    ],
) -> dict[str, Any]:
    try:
        share_url = share_url_from_text(request.share_text)
        platform = resolve_platform(share_url, request.platform)
        payload = (
            await resolve_tiktok_share_url(share_url, media_registry)
            if platform == "tiktok"
            else await resolve_share_text(
                request.share_text,
                cookie_store,
                media_registry,
                direct_aweme_id=request.aweme_id,
            )
        )
        return await _attach_local_reference_video(
            payload, media_registry, shot_detection_service
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"解析失败：{exc}",
        ) from exc


async def _attach_local_reference_video(
    payload: dict[str, Any],
    media_registry: MediaRegistry,
    shot_detection_service: ShotDetectionService,
) -> dict[str, Any]:
    """Download the resolved video while its signed CDN URL is still valid."""
    video = payload.get("video")
    aweme_id = payload.get("aweme_id")
    if not isinstance(video, dict) or not isinstance(aweme_id, str):
        return payload
    proxy_url = video.get("proxy_url")
    match = re.fullmatch(r"/api/media/([a-f0-9]{32})/(\d+)", str(proxy_url))
    if match is None:
        return payload
    resource = media_registry.get(match.group(1), int(match.group(2)))
    if resource is None or resource.kind != "video":
        return payload
    try:
        stored = await shot_detection_service.capture_source(aweme_id, resource)
    except ShotDetectionError as exc:
        warnings = payload.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append(f"参考视频暂存失败：{exc}")
        return payload
    analysis_id = str(stored["analysis_id"])
    video["local_analysis_id"] = analysis_id
    video["local_proxy_url"] = f"/api/shot-detection/{analysis_id}/assets/source.mp4"
    return payload
