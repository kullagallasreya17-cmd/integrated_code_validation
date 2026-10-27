import logging
import os
from pathlib import PurePosixPath
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.agent import generate_report_and_recommendations


app = FastAPI(title="Report and Recommendation Agent", version="1.0.0")
logger = logging.getLogger(__name__)
MAX_INPUT_CHARACTERS = 300_000


class AnalyzeRequest(BaseModel):
    files: dict[str, str] = Field(min_length=1)

    @field_validator("files")
    @classmethod
    def validate_files(cls, files: dict[str, str]) -> dict[str, str]:
        for name, content in files.items():
            path = PurePosixPath(name.replace("\\", "/"))
            has_windows_drive = bool(path.parts) and len(path.parts[0]) == 2 and path.parts[0][1] == ":"
            if path.is_absolute() or has_windows_drive or ".." in path.parts or path.suffix.lower() != ".py":
                raise ValueError("Only relative Python source files are supported")
            if not isinstance(content, str):
                raise ValueError("Python file content must be text")
        if sum(len(content) for content in files.values()) > MAX_INPUT_CHARACTERS:
            raise ValueError("Project exceeds the AI report input limit")
        return files


class AnalyzeResponse(BaseModel):
    status: Literal["completed", "skipped"]
    code_report: dict = Field(default_factory=dict)
    recommendation_report: dict = Field(default_factory=dict)
    message: str | None = None


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "report-recommendation-service",
        "configured": bool(os.getenv("GEMINI_API_KEY")),
    }


@app.post(
    "/analyze",
    responses={502: {"description": "AI report/recommendation generation failed"}},
)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return AnalyzeResponse(status="skipped", message="Gemini API key is not configured.")

    try:
        code_report, recommendation_report = await generate_report_and_recommendations(
            request.files,
            api_key,
            os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        )
    except Exception as exc:  # noqa: BLE001 - keep provider details and secrets out of API responses
        logger.warning("AI report/recommendation request failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="AI report/recommendation generation failed") from exc

    return AnalyzeResponse(
        status="completed",
        code_report=code_report,
        recommendation_report=recommendation_report,
    )