from __future__ import annotations

import asyncio
import json
import re
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from backend.app.dependencies import (
    get_media_registry,
    get_replica_playbook_service,
    get_scene_package_service,
    get_seedance_workspace_service,
    get_shot_detection_service,
    get_storyboard_chunk_service,
    get_storyboard_script_service,
)
from backend.app.schemas.requests import (
    SeedanceAnchorImageBindingRequest,
    SeedanceAnchorImageRequest,
    SeedanceTaskSubmitRequest,
    SeedanceWorkspaceRequest,
    ShotDetectionRequest,
    StoryboardScriptRequest,
)
from backend.app.services.media import MediaRegistry
from backend.app.services.replica_analysis import (
    ReplicaAnalysisError,
    ReplicaAnalysisModelError,
    ReplicaAnalysisNotReadyError,
    ReplicaPlaybookService,
    ScenePackageService,
)
from backend.app.services.storyboard import StoryboardChunkService, StoryboardScriptService
from backend.app.services.seedance import (
    SeedanceConfigurationError,
    SeedanceProviderError,
    SeedanceWorkspaceError,
    SeedanceWorkspaceService,
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
    if request.local_analysis_id:
        try:
            payload = await service.detect_saved_source(
                request.aweme_id, request.local_analysis_id
            )
            payload["asset_base_url"] = (
                f"/api/shot-detection/{request.local_analysis_id}/assets"
            )
            return payload
        except ShotDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        except ShotDetectionError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except ShotDetectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/shot-detection/{analysis_id}/replica-playbook")
async def create_replica_playbook(
    analysis_id: str,
    package_service: Annotated[ScenePackageService, Depends(get_scene_package_service)],
    storyboard_service: Annotated[
        StoryboardScriptService, Depends(get_storyboard_script_service)
    ],
    playbook_service: Annotated[
        ReplicaPlaybookService, Depends(get_replica_playbook_service)
    ],
) -> dict[str, Any]:
    try:
        return await playbook_service.build(
            analysis_id,
            package_service.load(analysis_id),
            storyboard_service.load(analysis_id),
        )
    except ReplicaAnalysisNotReadyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ReplicaAnalysisModelError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    except ReplicaAnalysisError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/shot-detection/{analysis_id}/saved-state")
async def get_saved_analysis_state(
    analysis_id: str,
    detection_service: Annotated[
        ShotDetectionService, Depends(get_shot_detection_service)
    ],
    storyboard_service: Annotated[
        StoryboardScriptService, Depends(get_storyboard_script_service)
    ],
    playbook_service: Annotated[
        ReplicaPlaybookService, Depends(get_replica_playbook_service)
    ],
) -> dict[str, Any]:
    """Restore completed artifacts only; this endpoint never starts model work."""
    detection = detection_service.load(analysis_id)
    if detection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="已保存的自动分镜不存在或已过期")
    detection["asset_base_url"] = f"/api/shot-detection/{analysis_id}/assets"

    try:
        storyboard_script: dict[str, Any] | None = storyboard_service.load(analysis_id)
    except ReplicaAnalysisNotReadyError:
        storyboard_script = None
    try:
        replica_playbook: dict[str, Any] | None = playbook_service.load(analysis_id)
    except ReplicaAnalysisNotReadyError:
        replica_playbook = None

    return {
        "detection": detection,
        "storyboard_script": storyboard_script,
        "replica_playbook": replica_playbook,
    }


@router.get("/shot-detection/{analysis_id}/seedance-workspace")
def get_seedance_workspace(
    analysis_id: str,
    service: Annotated[SeedanceWorkspaceService, Depends(get_seedance_workspace_service)],
) -> dict[str, Any]:
    try:
        return service.get_workspace(analysis_id)
    except SeedanceWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/shot-detection/{analysis_id}/seedance-workspace")
def save_seedance_workspace(
    analysis_id: str,
    request: SeedanceWorkspaceRequest,
    service: Annotated[SeedanceWorkspaceService, Depends(get_seedance_workspace_service)],
) -> dict[str, Any]:
    try:
        return service.save_workspace(analysis_id, request.model_dump())
    except SeedanceWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/shot-detection/{analysis_id}/seedance-generation-review")
async def get_seedance_generation_review(
    analysis_id: str,
    service: Annotated[SeedanceWorkspaceService, Depends(get_seedance_workspace_service)],
) -> dict[str, Any]:
    """Prepare the exact video, image and prompt submission package without a model call."""
    try:
        return await service.get_generation_review(analysis_id)
    except SeedanceWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/shot-detection/{analysis_id}/seedance-anchor-images")
async def generate_seedance_anchor_image(
    analysis_id: str,
    request: SeedanceAnchorImageRequest,
    service: Annotated[SeedanceWorkspaceService, Depends(get_seedance_workspace_service)],
) -> dict[str, Any]:
    """Explicitly create one billable Seedream visual anchor per storyboard segment."""
    try:
        return await service.generate_anchor_image(
            analysis_id, request.segment_id, force=request.force
        )
    except SeedanceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SeedanceProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SeedanceWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/shot-detection/{analysis_id}/seedance-anchor-images/preview")
def get_seedance_anchor_image_previews(
    analysis_id: str,
    service: Annotated[SeedanceWorkspaceService, Depends(get_seedance_workspace_service)],
) -> dict[str, Any]:
    """Show the source contact sheet and exact image-edit prompt without calling a model."""
    try:
        return service.get_anchor_image_previews(analysis_id)
    except SeedanceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SeedanceWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/shot-detection/{analysis_id}/seedance-anchor-images/{segment_id}")
async def bind_seedance_anchor_image(
    analysis_id: str,
    segment_id: int,
    request: SeedanceAnchorImageBindingRequest,
    service: Annotated[SeedanceWorkspaceService, Depends(get_seedance_workspace_service)],
) -> dict[str, Any]:
    """Bind a user-uploaded/selected processed image as a segment visual anchor."""
    try:
        return await service.bind_anchor_image(
            analysis_id, segment_id, request.file_id
        )
    except SeedanceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SeedanceProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SeedanceWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/shot-detection/{analysis_id}/ark-files")
async def list_ark_files(
    analysis_id: str,
    service: Annotated[SeedanceWorkspaceService, Depends(get_seedance_workspace_service)],
) -> dict[str, Any]:
    try:
        service._validate_analysis_id(analysis_id)
        return await service.list_files(analysis_id)
    except SeedanceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SeedanceProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SeedanceWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/shot-detection/{analysis_id}/ark-files")
async def upload_ark_file(
    analysis_id: str,
    file: Annotated[UploadFile, File(description="上传到方舟的图片或视频")],
    service: Annotated[SeedanceWorkspaceService, Depends(get_seedance_workspace_service)],
) -> dict[str, Any]:
    try:
        service._validate_analysis_id(analysis_id)
        return await service.upload_file(analysis_id, file)
    except SeedanceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SeedanceProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SeedanceWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/shot-detection/{analysis_id}/ark-files/{file_id}/refresh")
async def refresh_ark_file(
    analysis_id: str,
    file_id: str,
    service: Annotated[SeedanceWorkspaceService, Depends(get_seedance_workspace_service)],
) -> dict[str, Any]:
    try:
        service._validate_analysis_id(analysis_id)
        return await service.refresh_file(analysis_id, file_id)
    except SeedanceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SeedanceProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SeedanceWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/shot-detection/{analysis_id}/seedance-tasks")
async def submit_seedance_task(
    analysis_id: str,
    request: SeedanceTaskSubmitRequest,
    service: Annotated[SeedanceWorkspaceService, Depends(get_seedance_workspace_service)],
) -> dict[str, Any]:
    """Submit one explicitly selected video segment; this endpoint can incur charges."""
    try:
        return await service.submit_task(analysis_id, request.segment_id)
    except SeedanceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SeedanceProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SeedanceWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/shot-detection/{analysis_id}/seedance-tasks/{local_task_id}/refresh")
async def refresh_seedance_task(
    analysis_id: str,
    local_task_id: str,
    service: Annotated[SeedanceWorkspaceService, Depends(get_seedance_workspace_service)],
) -> dict[str, Any]:
    try:
        return await service.refresh_task(analysis_id, local_task_id)
    except SeedanceConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SeedanceProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SeedanceWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/shot-detection/{analysis_id}/seedance-tasks/compose")
async def compose_seedance_tasks(
    analysis_id: str,
    service: Annotated[SeedanceWorkspaceService, Depends(get_seedance_workspace_service)],
) -> dict[str, Any]:
    """Locally combine completed renders with the original mixed audio track."""
    try:
        return await service.compose_completed_video(analysis_id)
    except SeedanceWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/shot-detection/{analysis_id}/storyboard-script/stream")
async def stream_storyboard_script(
    analysis_id: str,
    request: StoryboardScriptRequest,
    package_service: Annotated[ScenePackageService, Depends(get_scene_package_service)],
    chunk_service: Annotated[StoryboardChunkService, Depends(get_storyboard_chunk_service)],
    script_service: Annotated[StoryboardScriptService, Depends(get_storyboard_script_service)],
) -> StreamingResponse:
    queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

    async def report_segment(
        segment: dict[str, Any], completed: int, total: int
    ) -> None:
        await queue.put(
            (
                "segment",
                {"segment": segment, "completed": completed, "total": total},
            )
        )

    async def run() -> None:
        try:
            await queue.put(("progress", {"message": "正在准备关键帧与带时间戳的转写"}))
            packages = await package_service.create(analysis_id, request.context)
            await queue.put(("progress", {"message": "正在按不超过 15 秒的规则生成分段分镜图"}))
            manifest = await chunk_service.create(analysis_id, packages)
            await queue.put(("progress", {"message": "正在逐段生成完整分镜脚本"}))
            result = await script_service.build(
                analysis_id,
                manifest,
                request.context,
                report_segment,
                request.force,
            )
            await queue.put(("completed", {"result": result, "manifest": manifest}))
        except ReplicaAnalysisError as exc:
            await queue.put(("error", {"message": str(exc)}))
        except Exception:
            await queue.put(("error", {"message": "分段分镜脚本生成出现未知错误"}))
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
