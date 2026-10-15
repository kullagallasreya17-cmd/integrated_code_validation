from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Finding(BaseModel):
    file: str
    line: int | None = None
    type: str = "bug"
    severity: str = "medium"
    message: str


class CodeFile(BaseModel):
    path: str
    content: str


class RepairRequest(BaseModel):
    project_id: str = "local-project"
    language: str = "python"
    files: list[CodeFile] = Field(min_length=1)
    findings: list[Finding] = Field(default_factory=list)

    @field_validator("files")
    @classmethod
    def validate_files(cls, files: list[CodeFile]) -> list[CodeFile]:
        paths = []
        for file in files:
            normalized = file.path.replace("\\", "/").strip()
            parts = normalized.split("/")
            has_windows_drive = bool(parts) and len(parts[0]) == 2 and parts[0][1] == ":"
            if not normalized or normalized.startswith("/") or has_windows_drive or ".." in parts:
                raise ValueError("Project file paths must be relative and stay inside the project")
            if not normalized.lower().endswith(".py"):
                raise ValueError("Only Python source files are supported")
            paths.append(normalized)
        if len(paths) != len(set(paths)):
            raise ValueError("Project files must have unique paths")
        return [CodeFile(path=path, content=file.content) for path, file in zip(paths, files)]


class FileRepair(BaseModel):
    path: str
    original_code: str
    regenerated_code: str
    changed: bool
    explanation: str


class RepairResponse(BaseModel):
    status: Literal["completed", "partial", "failed"]
    repairs: list[FileRepair]
    unresolved_findings: list[Finding]
    validation_status: str