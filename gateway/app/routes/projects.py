from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, Form, UploadFile

from shared.schemas.project import ProjectMeta

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectMeta)
async def create_project(project: ProjectMeta) -> ProjectMeta:
    """Accept project metadata using the shared project contract."""
    return project


@router.post("/upload", response_model=ProjectMeta)
async def upload_project(
    name: str = Form(...),
    files: list[UploadFile] = File(...),
) -> ProjectMeta:
    """Create project metadata for an uploaded project.

    Files are not persisted yet; the endpoint currently reports their count
    while keeping the response compatible with the shared project contract.
    """
    return ProjectMeta(
        project_id=f"proj-{uuid4().hex}",
        name=name,
        file_count=len(files),
        created_at=datetime.now(timezone.utc).isoformat(),
    )