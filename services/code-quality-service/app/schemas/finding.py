"""
Re-exports the shared Finding contract plus the request shape this
service accepts. Keeping the import local (instead of every route
reaching into `shared` directly) makes it a one-line change if the
shared package path ever moves.
"""
from pathlib import PurePosixPath
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from shared.schemas.finding import Finding, FindingsResponse, Severity, FindingCategory  # noqa: F401


class ProjectFile(BaseModel):
    path: str
    content: str

    @field_validator("path")
    @classmethod
    def validate_python_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        path = PurePosixPath(normalized)
        has_windows_drive = len(path.parts) > 0 and len(path.parts[0]) == 2 and path.parts[0][1] == ":"
        if not normalized or path.is_absolute() or has_windows_drive or ".." in path.parts:
            raise ValueError("file path must be a relative path within the project")
        if path.suffix.lower() != ".py":
            raise ValueError("code quality analysis currently supports Python .py files only")
        return "/".join(path.parts)


class AnalyzeRequest(BaseModel):
    project_id: str
    files: list[ProjectFile]
    project_context: dict = Field(default_factory=dict)
    tools: Optional[list[str]] = Field(
        default=None,
        description="Subset of ['ruff','pylint','radon'] to run. Defaults to all three.",
    )

    @field_validator("files")
    @classmethod
    def validate_unique_file_paths(cls, value: list[ProjectFile]) -> list[ProjectFile]:
        paths = [file.path for file in value]
        if len(paths) != len(set(paths)):
            raise ValueError("project files must have unique paths")
        return value

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("project_id must not be empty")
        return value

    @field_validator("tools")
    @classmethod
    def validate_tools(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return value
        supported = {"ruff", "pylint", "radon"}
        unknown = set(value) - supported
        if unknown:
            raise ValueError(f"unsupported analysis tool(s): {', '.join(sorted(unknown))}")
        if len(value) != len(set(value)):
            raise ValueError("tools must not contain duplicates")
        if not value:
            raise ValueError("tools must contain at least one analyzer")
        return value
