from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalysisRunRecord,
    FindingRecord,
    ProjectRecord,
    RepairRecord,
    ReportRecord,
    ToolResultRecord,
    ValidationRecord,
    WorkflowEventRecord,
)
from app.services.store import save_project


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def prepare_project(
    session: AsyncSession,
    project_id: str,
    files: list[dict[str, str]],
    name: str = "Python project",
) -> ProjectRecord:
    current = await session.get(ProjectRecord, project_id)
    if current is not None:
        name = current.name
    return await save_project(session, project_id, name, files)


async def create_run(
    session: AsyncSession,
    project_id: str,
    workflow_id: str,
    tools: list[str] | None,
    project_context: dict,
) -> AnalysisRunRecord:
    record = AnalysisRunRecord(
        run_id=f"run-{uuid4().hex}",
        project_id=project_id,
        workflow_id=workflow_id,
        status="submitted",
        progress="queued",
        tools=tools or [],
        project_context=project_context,
    )
    session.add(record)
    session.add(WorkflowEventRecord(
        run_id=record.run_id,
        event="submitted",
        status="submitted",
        message="Analysis submitted to the orchestrator.",
        payload={"workflow_id": workflow_id},
    ))
    await session.flush()
    return record


async def latest_run_for_workflow(session: AsyncSession, workflow_id: str) -> AnalysisRunRecord | None:
    return await session.scalar(
        select(AnalysisRunRecord)
        .where(AnalysisRunRecord.workflow_id == workflow_id)
        .order_by(AnalysisRunRecord.started_at.desc())
        .limit(1)
    )


async def persist_snapshot(
    session: AsyncSession,
    run: AnalysisRunRecord,
    snapshot: dict,
) -> None:
    previous = (run.status, run.progress)
    status = snapshot.get("status")
    if isinstance(status, str):
        run.status = status
        project = await session.get(ProjectRecord, run.project_id)
        if project is not None:
            project.status = {
                "submitted": "analyzing",
                "working": "analyzing",
                "completed": "completed",
                "failed": "failed",
                "cancelled": "failed",
            }.get(status, project.status)
    progress = snapshot.get("progress")
    if isinstance(progress, str):
        run.progress = progress
    error = snapshot.get("error")
    if isinstance(error, str):
        run.error = error

    result = snapshot.get("result")
    if isinstance(result, dict):
        run.result = result
        report = result.get("final_report")
        if isinstance(report, dict):
            run.validation_status = result.get("validation_status") or report.get("validation_status")
            await _persist_result_children(session, run.run_id, result, report)

    if (run.status, run.progress) != previous:
        session.add(WorkflowEventRecord(
            run_id=run.run_id,
            event=run.progress or "workflow",
            status=str(snapshot.get("stage_status") or run.status),
            message=snapshot.get("message") or snapshot.get("error"),
            payload={key: value for key, value in snapshot.items() if key != "result"},
        ))

    if run.status in {"completed", "failed", "cancelled"}:
        run.completed_at = run.completed_at or now_utc()
    await session.flush()


async def _persist_result_children(
    session: AsyncSession,
    run_id: str,
    result: dict,
    report: dict,
) -> None:
    for model in (FindingRecord, ToolResultRecord, RepairRecord, ValidationRecord, ReportRecord):
        await session.execute(delete(model).where(model.run_id == run_id))

    findings = result.get("findings") or report.get("findings") or []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            continue
        session.add(FindingRecord(
            run_id=run_id,
            finding_id=str(finding.get("finding_id") or f"{run_id}-finding-{index}"),
            agent=finding.get("agent") or finding.get("detected_by"),
            category=str(finding.get("category") or "unknown"),
            severity=str(finding.get("severity") or "info"),
            file_path=finding.get("file"),
            line_number=finding.get("line_number"),
            status=str(finding.get("status") or "open"),
            payload=finding,
        ))

    quality = result.get("quality_summary") or report.get("quality_summary") or {}
    tool_runs = quality.get("tool_runs") or []
    for tool in tool_runs:
        if not isinstance(tool, dict) or not tool.get("tool"):
            continue
        session.add(ToolResultRecord(
            run_id=run_id,
            tool_name=str(tool["tool"]),
            status=str(tool.get("status") or "unknown"),
            duration_ms=tool.get("duration_ms"),
            error=tool.get("error"),
            payload=tool,
        ))

    for index, repair in enumerate(result.get("repair_attempts") or report.get("repair_attempts") or [], start=1):
        if isinstance(repair, dict):
            iteration = int(repair.get("iteration") or index)
            session.add(RepairRecord(
                run_id=run_id,
                iteration=iteration,
                status=str(repair.get("outcome") or repair.get("status") or "unknown"),
                payload=repair,
            ))

    validation = result.get("validation_results") or report.get("validation_results") or {}
    if isinstance(validation, dict) and validation:
        session.add(ValidationRecord(
            run_id=run_id,
            passed=validation.get("passed") if isinstance(validation.get("passed"), bool) else None,
            payload=validation,
        ))

    session.add(ReportRecord(run_id=run_id, payload=report))