from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field, field_validator

from shared.schemas.project import ProjectMeta

router = APIRouter(prefix="/projects", tags=["projects"])
api_router = APIRouter(prefix="/api/projects", tags=["projects"])

PROJECT_FILES: dict[str, list[dict[str, str]]] = {}


class ProjectCreate(BaseModel):
    name: str = "Untitled project"
    files: list[dict[str, str]] = Field(default_factory=list)
    source_code: str | None = None
    project_context: dict = Field(default_factory=dict)

    @field_validator("files")
    @classmethod
    def validate_files(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        paths = [item.get("path", "").replace("\\", "/").strip() for item in value]
        if any(not path or path.startswith("/") or ".." in path.split("/") for path in paths):
            raise ValueError("project file paths must be relative")
        if len(paths) != len(set(paths)):
            raise ValueError("project files must have unique paths")
        return [{**item, "path": path} for item, path in zip(value, paths)]


def _create_project(project: ProjectCreate) -> ProjectMeta:
    project_id = f"proj-{uuid4().hex}"
    files = [
        {"path": item["path"], "content": item["content"]}
        for item in project.files
        if item.get("path") and isinstance(item.get("content"), str)
    ]
    if not files and project.source_code:
        files = [{"path": "main.py", "content": project.source_code}]
    PROJECT_FILES[project_id] = files
    return ProjectMeta(
        project_id=project_id,
        name=project.name,
        file_count=len(files),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@router.post("", response_model=ProjectMeta)
async def create_project(project: ProjectMeta) -> ProjectMeta:
    """Accept project metadata using the shared project contract."""
    return project


@api_router.post("", response_model=ProjectMeta)
async def create_api_project(project: ProjectCreate) -> ProjectMeta:
    return _create_project(project)


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