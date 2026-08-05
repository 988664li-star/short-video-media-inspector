from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.app.dependencies import get_media_registry
from backend.app.services.media import (
    MediaRegistry,
    create_media_response,
)


router = APIRouter()


@router.get("/{session_id}/{resource_index}")
async def proxy_media(
    session_id: str,
    resource_index: int,
    media_registry: Annotated[MediaRegistry, Depends(get_media_registry)],
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> StreamingResponse:
    resource = media_registry.get(session_id, resource_index)
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="媒体地址已过期，请重新解析分享链接",
        )
    return await create_media_response(resource, range_header)
