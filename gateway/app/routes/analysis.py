import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse

from app.config import settings
from app.routes.projects import PROJECT_FILES
from uuid import uuid4


class ProjectFileIn(BaseModel):
    path: str
    content: str


class StartAnalysisRequest(BaseModel):
    project_id: str
    files: list[ProjectFileIn]
    project_context: dict = Field(default_factory=dict)
    tools: list[str] | None = None

router = APIRouter(prefix="/analysis", tags=["analysis"])
api_router = APIRouter(prefix="/api", tags=["analysis"])
RUN_PROJECTS: dict[str, str] = {}


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


@api_router.post("/analysis")
async def start_api_analysis(request: dict):
    project_id = request.get("project_id")
    if not project_id or project_id not in PROJECT_FILES:
        raise HTTPException(status_code=404, detail="project not found")
    run_id = f"run-{uuid4().hex}"
    RUN_PROJECTS[run_id] = project_id
    payload = {
        "project_id": project_id,
        "files": PROJECT_FILES[project_id],
        "project_context": request.get("project_context", {}),
        "tools": request.get("tools"),
    }
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(
                f"{settings.orchestrator_url.rstrip('/')}/workflow/start",
                json=payload,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Orchestrator unavailable") from exc
    return {"run_id": run_id, "project_id": project_id, "status": "started"}


async def _api_status(run_id: str) -> dict:
    project_id = RUN_PROJECTS.get(run_id, run_id)
    return await analysis_status(project_id)


@api_router.get("/analysis/{run_id}/status")
async def api_analysis_status(run_id: str):
    status = await _api_status(run_id)
    return {
        "run_id": run_id,
        "project_id": status.get("project_id"),
        "status": status.get("status", "failed"),
        "current_agent": status.get("progress"),
        "error": status.get("error"),
    }


@api_router.get("/analysis/{run_id}/results")
async def api_analysis_results(run_id: str):
    status = await _api_status(run_id)
    result = status.get("result", {})
    findings = result.get("findings", [])
    return {
        "run_id": run_id,
        "project_id": status.get("project_id"),
        "status": status.get("status", "failed"),
        "findings": findings,
        "summary": result.get("final_report", {}).get("findings_summary", {}),
        "result": result,
        "error": status.get("error"),
    }


@api_router.post(
    "/agents/code-quality/analyze",
    responses={502: {"description": "Code Quality service unavailable"}},
)
async def api_code_quality_analysis(request: dict):
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(
                f"{settings.quality_service_url.rstrip('/')}/analyze",
                json=request,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Code Quality service unavailable") from exc