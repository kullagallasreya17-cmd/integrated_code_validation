from pydantic import BaseModel, Field, field_validator


class ProjectFileIn(BaseModel):
    path: str
    content: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        if not normalized or normalized.startswith("/") or ".." in normalized.split("/"):
            raise ValueError("file path must be relative and stay inside the project")
        return normalized


class StartAnalysisRequest(BaseModel):
    project_id: str
    files: list[ProjectFileIn]
    project_context: dict = Field(default_factory=dict)
    tools: list[str] | None = None

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("project_id must not be empty")
        return value

    @field_validator("files")
    @classmethod
    def validate_files(cls, value: list[ProjectFileIn]) -> list[ProjectFileIn]:
        if not value:
            raise ValueError("at least one project file is required")
        paths = [item.path for item in value]
        if len(paths) != len(set(paths)):
            raise ValueError("project files must have unique paths")
        return value


class WorkflowRunResponse(BaseModel):
    project_id: str
    validation_status: str
    retry_count: int
    findings: list[dict]
    final_report: dict
