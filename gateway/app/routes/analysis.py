import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionFactory, get_session
from app.models import AnalysisRunRecord, ProjectRecord
from app.services.run_store import (
    create_run,
    latest_run_for_workflow,
    persist_snapshot,
    prepare_project,
)
from app.services.store import file_payload, project_files


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


async def _create_workflow_run(
    project_id: str,
    files: list[dict[str, str]],
    project_context: dict,
    tools: list[str] | None,
    session: AsyncSession,
) -> dict:
    await prepare_project(session, project_id, files)
    run = await create_run(session, project_id, project_id, tools, project_context)
    await session.commit()
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(
                f"{settings.orchestrator_url.rstrip('/')}/workflow/start",
                json={
                    "project_id": project_id,
                    "files": files,
                    "project_context": project_context,
                    "tools": tools,
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        run.status = "failed"
        run.error = "The orchestrator rejected this analysis request."
        await session.commit()
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.HTTPError as exc:
        run.status = "failed"
        run.error = "The orchestrator is unavailable."
        await session.commit()
        raise HTTPException(status_code=502, detail="Orchestrator unavailable") from exc

    started = response.json()
    return {**started, "project_id": project_id, "run_id": run.run_id}


@router.post("/run")
async def run_analysis(
    request: StartAnalysisRequest,
    session: AsyncSession = Depends(get_session),
):
    return await _create_workflow_run(
        request.project_id,
        [item.model_dump() for item in request.files],
        request.project_context,
        request.tools,
        session,
    )


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
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            try:
                                snapshot = __import__("json").loads(line[5:].strip())
                                async with SessionFactory() as session:
                                    run = await latest_run_for_workflow(session, project_id)
                                    if run is not None:
                                        await persist_snapshot(session, run, snapshot)
                                        await session.commit()
                            except (ValueError, TypeError):
                                pass
                        yield f"{line}\n"
                        if not line:
                            yield "\n"
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
async def start_api_analysis(request: dict, session: AsyncSession = Depends(get_session)):
    project_id = request.get("project_id")
    if not project_id or await session.get(ProjectRecord, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    project_source_files = [file_payload(item) for item in await project_files(session, project_id)]
    started = await _create_workflow_run(
        project_id,
        project_source_files,
        request.get("project_context", {}),
        request.get("tools"),
        session,
    )
    return {**started, "status": "started"}


async def _api_status(run_id: str, session: AsyncSession) -> dict:
    run = await session.get(AnalysisRunRecord, run_id)
    workflow_id = run.workflow_id if run is not None else run_id
    status = await analysis_status(workflow_id)
    if run is not None:
        await persist_snapshot(session, run, status)
        await session.commit()
        return {**status, "run_id": run.run_id, "project_id": run.project_id}
    return status


@api_router.get("/analysis/{run_id}/status")
async def api_analysis_status(run_id: str, session: AsyncSession = Depends(get_session)):
    status = await _api_status(run_id, session)
    return {
        "run_id": status.get("run_id", run_id),
        "project_id": status.get("project_id"),
        "status": status.get("status", "failed"),
        "current_agent": status.get("progress"),
        "started_at": status.get("started_at"),
        "completed_at": status.get("completed_at"),
        "error": status.get("error"),
    }


@api_router.get("/analysis/{run_id}/results")
async def api_analysis_results(run_id: str, session: AsyncSession = Depends(get_session)):
    status = await _api_status(run_id, session)
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