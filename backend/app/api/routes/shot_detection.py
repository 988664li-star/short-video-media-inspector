from __future__ import annotations

import asyncio
import json
import re
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse

from backend.app.dependencies import (
    get_media_registry,
    get_replica_playbook_service,
    get_scene_package_service,
    get_scene_visual_analysis_service,
    get_shot_detection_service,
)
from backend.app.schemas.requests import SceneAnalysisRequest, ShotDetectionRequest
from backend.app.services.media import MediaRegistry
from backend.app.services.replica_analysis import (
    ReplicaAnalysisError,
    ReplicaAnalysisModelError,
    ReplicaAnalysisNotReadyError,
    ReplicaPlaybookService,
    ScenePackageService,
    SceneVisualAnalysisService,
)
from backend.app.services.shot_detection import (
    ShotDecodeError,
    ShotDetectionError,
    ShotDetectionService,
    ShotMediaDownloadError,
)


router = APIRouter()
MEDIA_PROXY_PATTERN = re.compile(r"^/api/media/([a-f0-9]{32})/(\d+)$")


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/shot-detection")
async def detect_shots(
    request: ShotDetectionRequest,
    media_registry: Annotated[MediaRegistry, Depends(get_media_registry)],
    service: Annotated[ShotDetectionService, Depends(get_shot_detection_service)],
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
    if resource.kind != "video":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前媒体不是视频，无法进行分镜识别",
        )

    try:
        payload = await service.detect(request.aweme_id, resource)
        analysis_id = payload.get("analysis_id")
        if isinstance(analysis_id, str):
            payload["asset_base_url"] = f"/api/shot-detection/{analysis_id}/assets"
        return payload
    except ShotMediaDownloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ShotDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ShotDetectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/shot-detection/{analysis_id}/scene-analysis")
async def create_scene_analysis(
    analysis_id: str,
    request: SceneAnalysisRequest,
    package_service: Annotated[ScenePackageService, Depends(get_scene_package_service)],
    visual_service: Annotated[
        SceneVisualAnalysisService, Depends(get_scene_visual_analysis_service)
    ],
) -> dict[str, Any]:
    try:
        packages = await package_service.create(analysis_id, request.context)
        return await visual_service.analyze(analysis_id, packages, force=request.force)
    except ReplicaAnalysisNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ReplicaAnalysisModelError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    except ReplicaAnalysisError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/shot-detection/{analysis_id}/scene-analysis/stream")
async def stream_scene_analysis(
    analysis_id: str,
    request: SceneAnalysisRequest,
    package_service: Annotated[ScenePackageService, Depends(get_scene_package_service)],
    visual_service: Annotated[
        SceneVisualAnalysisService, Depends(get_scene_visual_analysis_service)
    ],
) -> StreamingResponse:
    queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

    async def report(stage: str, message: str) -> None:
        await queue.put(("progress", {"stage": stage, "message": message}))

    async def report_scene(
        analysis: dict[str, Any], completed: int, total: int
    ) -> None:
        await queue.put(
            (
                "scene",
                {"analysis": analysis, "completed": completed, "total": total},
            )
        )

    async def run() -> None:
        try:
            await report("starting", "正在准备镜头视觉分析")
            packages = await package_service.create(
                analysis_id, request.context, report
            )
            await report("visual", "正在逐镜头分析关键帧与口播")
            result = await visual_service.analyze(
                analysis_id, packages, report_scene, request.force
            )
            await queue.put(("completed", {"result": result}))
        except ReplicaAnalysisError as exc:
            await queue.put(("error", {"message": str(exc)}))
        except Exception:
            await queue.put(("error", {"message": "镜头视觉分析出现未知错误"}))
        finally:
            await queue.put(("done", {}))

    async def event_stream() -> AsyncIterator[str]:
        task = asyncio.create_task(run())
        try:
            while True:
                event, payload = await queue.get()
                if event == "done":
                    break
                yield _sse_event(event, payload)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/shot-detection/{analysis_id}/replica-playbook")
async def create_replica_playbook(
    analysis_id: str,
    package_service: Annotated[ScenePackageService, Depends(get_scene_package_service)],
    visual_service: Annotated[
        SceneVisualAnalysisService, Depends(get_scene_visual_analysis_service)
    ],
    playbook_service: Annotated[
        ReplicaPlaybookService, Depends(get_replica_playbook_service)
    ],
) -> dict[str, Any]:
    try:
        return await playbook_service.build(
            analysis_id,
            package_service.load(analysis_id),
            visual_service.load(analysis_id),
        )
    except ReplicaAnalysisNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ReplicaAnalysisModelError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    except ReplicaAnalysisError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/shot-detection/{analysis_id}/assets/{asset_path:path}")
def get_scene_asset(
    analysis_id: str,
    asset_path: str,
    service: Annotated[ShotDetectionService, Depends(get_shot_detection_service)],
) -> FileResponse:
    path = service.get_scene_asset(analysis_id, asset_path)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分镜素材不存在")
    return FileResponse(path, headers={"Cache-Control": "no-store"})
