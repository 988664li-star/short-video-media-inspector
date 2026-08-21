"""API endpoints for persistent infinite-canvas projects."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from backend.app.core.config import settings
from backend.app.dependencies import (
    get_canvas_ai_service,
    get_canvas_media_extraction_service,
    get_canvas_project_service,
    get_canvas_replacement_analysis_service,
    get_canvas_replacement_task_service,
    get_canvas_video_service,
)
from backend.app.schemas.requests import (
    CanvasImageGenerateRequest,
    CanvasMediaExtractRequest,
    CanvasReplacementAnalysisRequest,
    CanvasReplacementCompositionRequest,
    CanvasReplacementPromptBuildRequest,
    CanvasReplacementTaskRefreshRequest,
    CanvasReplacementTaskSubmitRequest,
    CanvasVideoAssetRequest,
    CanvasProjectCreateRequest,
    CanvasProjectUpdateRequest,
    CanvasTextGenerateRequest,
)
from backend.app.services.canvas_projects import (
    CanvasAIError,
    CanvasAIService,
    CanvasAssetNotFoundError,
    CanvasMediaExtractionError,
    CanvasMediaExtractionService,
    CanvasMediaTooLargeError,
    CanvasVideoError,
    CanvasVideoService,
    CanvasProjectNotFoundError,
    CanvasProjectService,
    CanvasReplacementAnalysisError,
    CanvasReplacementAnalysisService,
    CanvasReplacementTaskError,
    CanvasReplacementTaskService,
)


router = APIRouter()
CanvasProjectDependency = Annotated[CanvasProjectService, Depends(get_canvas_project_service)]
CanvasAIDependency = Annotated[CanvasAIService, Depends(get_canvas_ai_service)]
CanvasMediaExtractionDependency = Annotated[
    CanvasMediaExtractionService, Depends(get_canvas_media_extraction_service)
]
CanvasVideoDependency = Annotated[CanvasVideoService, Depends(get_canvas_video_service)]
CanvasReplacementAnalysisDependency = Annotated[
    CanvasReplacementAnalysisService, Depends(get_canvas_replacement_analysis_service)
]
CanvasReplacementTaskDependency = Annotated[
    CanvasReplacementTaskService, Depends(get_canvas_replacement_task_service)
]


def _not_found(project_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"画布不存在：{project_id}",
    )


@router.get("/projects")
def list_projects(service: CanvasProjectDependency) -> dict[str, Any]:
    return {"projects": service.list_projects()}


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(
    request: CanvasProjectCreateRequest,
    service: CanvasProjectDependency,
) -> dict[str, Any]:
    return {"project": service.create_project(request.name)}


@router.post("/projects/default")
def get_or_create_default_project(service: CanvasProjectDependency) -> dict[str, Any]:
    return {"project": service.get_or_create_default_project()}


@router.get("/projects/{project_id}")
def get_project(project_id: str, service: CanvasProjectDependency) -> dict[str, Any]:
    try:
        return {"project": service.get_project(project_id)}
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc


@router.post("/projects/{project_id}")
def update_project(
    project_id: str,
    request: CanvasProjectUpdateRequest,
    service: CanvasProjectDependency,
) -> dict[str, Any]:
    try:
        return {"project": service.update_project(project_id, request.model_dump())}
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc


@router.post("/projects/{project_id}/generate-text")
async def generate_text(
    project_id: str,
    request: CanvasTextGenerateRequest,
    service: CanvasProjectDependency,
    ai_service: CanvasAIDependency,
) -> dict[str, Any]:
    try:
        service.get_project(project_id)
        return await ai_service.generate_text(request.prompt, request.context)
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc
    except CanvasAIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/projects/{project_id}/generate-image")
async def generate_image(
    project_id: str,
    request: CanvasImageGenerateRequest,
    service: CanvasProjectDependency,
    ai_service: CanvasAIDependency,
) -> dict[str, Any]:
    try:
        service.get_project(project_id)
        result = await ai_service.generate_image(
            project_id,
            request.prompt,
            request.source_url or "",
            request.source_asset_ids,
            request.aspect_ratio,
        )
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc
    except CanvasAIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    asset = result["asset"]
    return {
        "asset": {
            **asset,
            "url": f"/api/canvas/projects/{project_id}/assets/{asset['id']}",
        },
        "model": result["model"],
    }


@router.post("/projects/{project_id}/extract-media")
async def extract_media(
    project_id: str,
    request: CanvasMediaExtractRequest,
    extraction_service: CanvasMediaExtractionDependency,
) -> dict[str, Any]:
    try:
        result = await extraction_service.extract(
            project_id,
            request.share_text,
            request.platform,
        )
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CanvasMediaTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except CanvasMediaExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"链接提取失败：{exc}",
        ) from exc
    return {
        **result,
        "outputs": {
            kind: {
                **output,
                "asset": (
                    {
                        **output["asset"],
                        "url": f"/api/canvas/projects/{project_id}/assets/{output['asset']['id']}",
                    }
                    if output["asset"]
                    else None
                ),
            }
            for kind, output in result["outputs"].items()
        },
    }


@router.post("/projects/{project_id}/video-shots")
async def split_video_by_shots(
    project_id: str,
    request: CanvasVideoAssetRequest,
    video_service: CanvasVideoDependency,
) -> dict[str, Any]:
    try:
        result = await video_service.split_by_shots(project_id, request.asset_id)
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc
    except CanvasVideoError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return {
        **result,
        "shots": [
            {
                **shot,
                "asset": {
                    **shot["asset"],
                    "url": f"/api/canvas/projects/{project_id}/assets/{shot['asset']['id']}",
                },
            }
            for shot in result["shots"]
        ],
    }


@router.post("/projects/{project_id}/video-keyframes")
async def extract_video_keyframes(
    project_id: str,
    request: CanvasVideoAssetRequest,
    video_service: CanvasVideoDependency,
) -> dict[str, Any]:
    try:
        result = await video_service.extract_keyframes(project_id, request.asset_id)
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc
    except CanvasVideoError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return {
        **result,
        "frames": [
            {
                **frame,
                "asset": {
                    **frame["asset"],
                    "url": f"/api/canvas/projects/{project_id}/assets/{frame['asset']['id']}",
                },
            }
            for frame in result["frames"]
        ],
    }


@router.post("/projects/{project_id}/replacement-analysis")
async def analyze_replaceable_subjects(
    project_id: str,
    request: CanvasReplacementAnalysisRequest,
    service: CanvasProjectDependency,
    analysis_service: CanvasReplacementAnalysisDependency,
) -> dict[str, Any]:
    try:
        service.get_project(project_id)
        result = await analysis_service.analyze(
            project_id,
            [shot.model_dump() for shot in request.shots],
        )
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc
    except CanvasReplacementAnalysisError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return {
        "keyframes": [
            {
                "shot_index": frame["shot_index"],
                "asset": {
                    **frame["asset"],
                    "url": f"/api/canvas/projects/{project_id}/assets/{frame['asset']['id']}",
                },
            }
            for frame in result["keyframes"]
        ],
        "objects": result["objects"],
    }


@router.post("/projects/{project_id}/replacement-prompts")
def build_replacement_prompts(
    project_id: str,
    request: CanvasReplacementPromptBuildRequest,
    service: CanvasProjectDependency,
    replacement_service: CanvasReplacementTaskDependency,
) -> dict[str, Any]:
    try:
        service.get_project(project_id)
        prompts = replacement_service.build_prompts(
            source_object_name=request.source_object_name,
            source_object_description=request.source_object_description,
            target_description=request.target_description,
            target_asset_ids=request.target_asset_ids,
            shots=[shot.model_dump() for shot in request.shots],
            actions=[action.model_dump() for action in request.actions],
        )
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc
    except CanvasReplacementTaskError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return {"prompts": prompts}


@router.post("/projects/{project_id}/replacement-tasks")
async def submit_replacement_tasks(
    project_id: str,
    request: CanvasReplacementTaskSubmitRequest,
    service: CanvasProjectDependency,
    replacement_service: CanvasReplacementTaskDependency,
) -> dict[str, Any]:
    try:
        service.get_project(project_id)
        results = await replacement_service.submit(
            project_id,
            model=request.model,
            target_asset_ids=request.target_asset_ids,
            shots=[shot.model_dump() for shot in request.shots],
            prompts=[prompt.model_dump() for prompt in request.prompts],
        )
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc
    except CanvasReplacementTaskError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return {"results": [_replacement_result_with_url(project_id, item) for item in results]}


@router.post("/projects/{project_id}/replacement-tasks/refresh")
async def refresh_replacement_task(
    project_id: str,
    request: CanvasReplacementTaskRefreshRequest,
    service: CanvasProjectDependency,
    replacement_service: CanvasReplacementTaskDependency,
) -> dict[str, Any]:
    try:
        service.get_project(project_id)
        result = await replacement_service.refresh(
            project_id,
            provider_task_id=request.provider_task_id,
            shot=request.shot.model_dump(),
            existing_result_asset_id=request.result_asset_id,
        )
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc
    except CanvasReplacementTaskError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return {"result": _replacement_result_with_url(project_id, result)}


@router.post("/projects/{project_id}/replacement-compositions")
async def compose_replacement_results(
    project_id: str,
    request: CanvasReplacementCompositionRequest,
    service: CanvasProjectDependency,
    video_service: CanvasVideoDependency,
) -> dict[str, Any]:
    try:
        service.get_project(project_id)
        result = await video_service.compose_replacements(
            project_id,
            shots=[shot.model_dump() for shot in request.shots],
            results=[item.model_dump() for item in request.results],
            source_audio_asset_id=request.source_audio_asset_id,
        )
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc
    except CanvasVideoError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    asset = result["asset"]
    return {
        **result,
        "asset": {**asset, "url": f"/api/canvas/projects/{project_id}/assets/{asset['id']}"},
    }


def _replacement_result_with_url(project_id: str, result: dict[str, Any]) -> dict[str, Any]:
    asset = result.get("result_asset")
    return {
        **result,
        "result_asset": (
            {**asset, "url": f"/api/canvas/projects/{project_id}/assets/{asset['id']}"}
            if isinstance(asset, dict) else None
        ),
    }


@router.get("/projects/{project_id}/assets")
def list_assets(project_id: str, service: CanvasProjectDependency) -> dict[str, Any]:
    try:
        return {"assets": [
            {**asset, "url": f"/api/canvas/projects/{project_id}/assets/{asset['id']}"}
            for asset in service.list_assets(project_id)
        ]}
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc


@router.post("/projects/{project_id}/assets", status_code=status.HTTP_201_CREATED)
async def upload_asset(
    project_id: str,
    service: CanvasProjectDependency,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    mime_type = file.content_type or "application/octet-stream"
    if not mime_type.startswith(("image/", "video/", "audio/")):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="仅支持图片、视频或音频素材")
    content = await file.read(settings.canvas_asset_max_bytes + 1)
    if len(content) > settings.canvas_asset_max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="素材文件过大")
    try:
        asset = service.save_asset(project_id, file.filename or "素材", mime_type, content)
    except CanvasProjectNotFoundError as exc:
        raise _not_found(project_id) from exc
    return {"asset": {**asset, "url": f"/api/canvas/projects/{project_id}/assets/{asset['id']}"}}


@router.get("/projects/{project_id}/assets/{asset_id}")
def get_asset(
    project_id: str,
    asset_id: str,
    service: CanvasProjectDependency,
) -> FileResponse:
    try:
        asset, path = service.get_asset_file(project_id, asset_id)
    except (CanvasProjectNotFoundError, CanvasAssetNotFoundError) as exc:
        raise _not_found(asset_id) from exc
    return FileResponse(path, media_type=asset["mime_type"], filename=asset["filename"])
