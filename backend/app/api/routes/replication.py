from typing import Annotated, Any

from fastapi import APIRouter, Depends

from backend.app.dependencies import get_replica_project_service
from backend.app.schemas.requests import ReplicaProjectRequest
from backend.app.services.replica_projects import ReplicaProjectService


router = APIRouter()
ReplicaProjectDependency = Annotated[ReplicaProjectService, Depends(get_replica_project_service)]


@router.get("/projects")
def list_projects(service: ReplicaProjectDependency) -> dict[str, Any]:
    return {"projects": service.list_projects()}


@router.post("/projects")
def save_project(
    request: ReplicaProjectRequest,
    service: ReplicaProjectDependency,
) -> dict[str, Any]:
    data = request.model_dump()
    project_id = data.pop("id", None)
    return {"project": service.save_project(data, project_id)}
