import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse

from app.config import settings


class ProjectFileIn(BaseModel):
    path: str
    content: str


class StartAnalysisRequest(BaseModel):
    project_id: str
    files: list[ProjectFileIn]
    project_context: dict = Field(default_factory=dict)
    tools: list[str] | None = None

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/run")
async def run_analysis(request: StartAnalysisRequest):
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(
                f"{settings.orchestrator_url.rstrip('/')}/workflow/start",
                json=request.model_dump(),
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=exc.response.text,
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Orchestrator unavailable") from exc

    return response.json()


@router.get("/stream/{project_id}")
async def stream_analysis(project_id: str):
    async def events():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "GET",
                    f"{settings.orchestrator_url.rstrip('/')}/workflow/stream/{project_id}",
                ) as response:
                    if response.status_code >= 400:
                        detail = await response.aread()
                        raise HTTPException(status_code=response.status_code, detail=detail.decode())
                    async for chunk in response.aiter_bytes():
                        yield chunk
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Orchestrator unavailable") from exc

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/status/{project_id}")
async def analysis_status(project_id: str):
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.get(
                f"{settings.orchestrator_url.rstrip('/')}/workflow/status/{project_id}"
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Orchestrator unavailable") from exc


@router.get("/{project_id}/findings")
async def analysis_findings(project_id: str):
    status = await analysis_status(project_id)
    result = status.get("result", {})
    return {
        "project_id": project_id,
        "findings": result.get("findings", []),
        "findings_count": len(result.get("findings", [])),
    }