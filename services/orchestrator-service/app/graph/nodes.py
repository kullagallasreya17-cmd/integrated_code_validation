"""
Individual LangGraph nodes. Each node takes the WorkflowState, does one
job, and returns a partial dict that LangGraph merges back into state.

Nodes only talk to other services through the `app/services/*_client.py`
clients — never by importing another team member's code directly.
"""
import asyncio
from datetime import datetime, timezone

from app.graph.state import WorkflowState
from app.services import (
    security_client,
    quality_client,
    bug_resource_client,
    repair_client,
    sandbox_client,
    validation_client,
)
from app.aggregation.finding_aggregator import aggregate
from app.config import settings
from app.analysis.python_structure import inspect_python_files
from app.reporting.report_builder import build_report


async def understand_project(state: WorkflowState) -> dict:
    """Light-weight project intake: just confirms we have files and sets
    initial counters. Kept separate from `analyze` so it's easy to later
    add real project-understanding (dependency graph, language detection)
    without touching the analysis fan-out logic."""
    files = state.get("project_files", {})
    structure = inspect_python_files(files)
    stage = {"stage": "understand", "status": "completed", "file_count": len(files)}
    return {
        "retry_count": 0,
        "repair_attempt": 0,
        "validation_status": "pending",
        "code_structure": structure,
        "analysis_id": state.get("analysis_id") or state.get("project_id"),
        "agent_errors": [],
        "stage_history": [stage],
        "workflow_trace": ["Workflow started", "Project understanding completed"],
        "error": None if files else "No project files supplied",
    }


async def analyze(state: WorkflowState) -> dict:
    """Fan out to Security, Code Quality, and Bug/Resource agents in
    parallel, then store each agent's raw findings on state."""
    files = state.get("project_files", {})
    context = state.get("project_context", {})
    project_id = state["project_id"]
    tools = state.get("tools")
    checks = _analysis_checks(context)
    security_enabled = checks is None or checks["security"]
    quality_enabled = checks is None or checks["code_quality"] or checks["complexity"]
    resource_enabled = checks is None or checks["bug_resource"]

    calls = []
    agents = []
    if security_enabled:
        agents.append("security")
        calls.append(security_client.analyze(project_id, files, context))
    if quality_enabled:
        agents.append("code_quality")
        calls.append(quality_client.analyze(project_id, files, context, tools))
    if resource_enabled:
        agents.append("bug_resource")
        calls.append(bug_resource_client.analyze(project_id, files, context))

    results = await asyncio.gather(*calls, return_exceptions=True)
    responses = {}
    for agent, result in zip(agents, results):
        if isinstance(result, Exception):
            responses[agent] = {"findings": [], "error": f"{agent} failed: {result}"}
        else:
            responses[agent] = result
    security_res = responses.get("security", {"findings": []})
    quality_res = responses.get("code_quality", {"findings": []})
    resource_res = responses.get("bug_resource", {"findings": []})

    agent_errors = [
        {"agent": agent, "error": result["error"]}
        for agent, result in (
            ("security", security_res),
            ("code_quality", quality_res),
            ("bug_resource", resource_res),
        )
        if result.get("error")
    ]
    agent_statuses = {
        "security": "skipped" if not security_enabled else "completed",
        "quality": "skipped" if not quality_enabled else "completed",
        "bug_resource": "skipped" if not resource_enabled else "completed",
    }
    for error in agent_errors:
        agent = error["agent"]
        if agent == "code_quality":
            agent_statuses["quality"] = "failed"
        elif agent in agent_statuses:
            agent_statuses[agent] = "failed"

    update = {
        "security_findings": security_res.get("findings", []),
        "quality_findings": quality_res.get("findings", []),
        "resource_findings": resource_res.get("findings", []),
        "agent_errors": agent_errors,
        "workflow_trace": [*state.get("workflow_trace", []), "Analysis agents completed"],
        "stage_history": [*state.get("stage_history", []), {
            "stage": "analyze",
            "status": "completed" if not agent_errors else "partial",
            "agent_errors": agent_errors,
            "agents": agent_statuses,
        }],
    }
    if quality_enabled:
        quality_summary = quality_res.get("quality_summary", {})
        update["quality_summary"] = quality_summary
        update["quality_gate_status"] = (
            quality_summary.get("quality_gate_status")
            or quality_summary.get("quality_gate", {}).get("status", "UNKNOWN")
        )
    return update


def _analysis_checks(project_context: dict | None) -> dict | None:
    """Return normalized user-selected checks, or None for legacy requests."""
    context = project_context or {}
    checks = context.get("analysis_checks")
    if not isinstance(checks, dict):
        return None
    return {
        "code_quality": bool(checks.get("code_quality", True)),
        "security": bool(checks.get("security", True)),
        "bug_resource": bool(checks.get("bug_resource", True)),
        "complexity": bool(checks.get("complexity", True)),
        "automated_repair": bool(checks.get("automated_repair", True)),
        "final_validation": bool(checks.get("final_validation", True)),
    }


async def aggregate_findings(state: WorkflowState) -> dict:
    findings = aggregate(
        state.get("security_findings", []),
        state.get("quality_findings", []),
        state.get("resource_findings", []),
    )
    return {
        "findings": findings,
        "workflow_trace": [*state.get("workflow_trace", []), "Findings aggregated"],
        "stage_history": [*state.get("stage_history", []), {
            "stage": "aggregate", "status": "completed", "finding_count": len(findings)
        }],
    }


async def explain_and_prioritize(state: WorkflowState) -> dict:
    """Create deterministic explanations and repair priority metadata."""
    findings = state.get("findings", [])
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    prioritized = sorted(
        findings,
        key=lambda finding: (
            severity_rank.get(finding.get("severity", "medium"), 2),
            0 if state.get("quality_gate_status") == "FAIL" and finding.get("category") == "code_quality" else 1,
            finding.get("file", ""),
            finding.get("line_number") or 0,
        ),
    )
    explanations = [
        {
            "finding_id": finding.get("finding_id"),
            "priority": index + 1,
            "root_cause": finding.get("description", "Reported analyzer issue"),
            "recommendation": finding.get("recommendation") or "Review and address the finding.",
        }
        for index, finding in enumerate(prioritized)
    ]
    return {
        "prioritized_findings": prioritized,
        "explanations": explanations,
        "workflow_trace": [*state.get("workflow_trace", []), "Findings prioritized"],
        "stage_history": [*state.get("stage_history", []), {
            "stage": "explain_prioritize", "status": "completed", "finding_count": len(prioritized)
        }],
    }


async def repair(state: WorkflowState) -> dict:
    """Calls the Fix & Regeneration service with the current findings."""
    files = state.get("repaired_code") or state.get("project_files", {})
    attempt = state.get("repair_attempt", 0) + 1

    try:
        result = await repair_client.repair(
            state["project_id"], files, state.get("findings", []), attempt
        )
    except Exception as exc:  # noqa: BLE001 - convert downstream failure to state
        result = {"repaired_files": [], "error": f"repair failed: {exc}"}
    repaired = {f["path"]: f["content"] for f in result.get("repaired_files", [])}

    repair_error = result.get("error")
    agent_errors = [*state.get("agent_errors", [])]
    if repair_error:
        agent_errors.append({"agent": "repair", "error": repair_error})
    repaired_files = repaired or files
    attempt_record = {
        "iteration": attempt,
        "mode": result.get("mode", "targeted"),
        "changed_files": [path for path in repaired_files if repaired_files[path] != files.get(path)],
        "outcome": "failed" if repair_error else "candidate",
        "error": repair_error,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "repaired_code": repaired_files,
        "repair_attempt": attempt,
        "repair_attempts": [*state.get("repair_attempts", []), attempt_record],
        "agent_errors": agent_errors,
        "workflow_trace": [*state.get("workflow_trace", []), f"Repair iteration {attempt} requested"],
        "stage_history": [*state.get("stage_history", []), {
            "stage": "repair", "status": "partial" if repair_error else "completed",
            "attempt": attempt,
        }],
    }


async def validate(state: WorkflowState) -> dict:
    """Runs the repaired code through the sandbox, then the validation
    service, and stores a pass/fail verdict."""
    files = state.get("repaired_code") or state.get("project_files", {})
    project_id = state["project_id"]

    # Execute in the isolated sandbox first so validation can reason
    # about real runtime behaviour, not just static checks.
    try:
        sandbox_result = await sandbox_client.execute(project_id, files)
    except Exception as exc:  # noqa: BLE001 - convert downstream failure to state
        sandbox_result = {"executed": False, "error": f"sandbox failed: {exc}"}
    if not sandbox_result.get("executed"):
        error = sandbox_result.get("error", "Sandbox execution failed")
        agent_errors = [*state.get("agent_errors", []), {"agent": "sandbox", "error": error}]
        return {
            "sandbox_result": sandbox_result,
            "validation_results": {"passed": False, "error": error},
            "validation_status": "failed",
            "agent_errors": agent_errors,
            "workflow_trace": [*state.get("workflow_trace", []), "Sandbox validation failed"],
            "stage_history": [*state.get("stage_history", []), {
                "stage": "validate", "status": "failed", "sandbox": "failed"
            }],
        }

    try:
        result = await validation_client.validate(project_id, files, state.get("findings", []))
    except Exception as exc:  # noqa: BLE001 - convert downstream failure to state
        result = {"passed": False, "error": f"validation failed: {exc}"}
    passed = bool(result.get("passed"))
    agent_errors = [*state.get("agent_errors", [])]
    if result.get("error"):
        agent_errors.append({"agent": "validation", "error": result["error"]})

    return {
        "sandbox_result": sandbox_result,
        "validation_results": result,
        "validation_status": "passed" if passed else "failed",
        "agent_errors": agent_errors,
        "workflow_trace": [*state.get("workflow_trace", []), "Validation completed"],
        "stage_history": [*state.get("stage_history", []), {
            "stage": "validate", "status": "passed" if passed else "failed"
        }],
    }


async def reanalyze(state: WorkflowState) -> dict:
    """Re-run the configured quality analyzer against the repair candidate."""
    files = state.get("repaired_code") or state.get("project_files", {})
    try:
        result = await quality_client.analyze(
            state["project_id"], files, state.get("project_context", {}), state.get("tools")
        )
        findings = result.get("findings", [])
        error = result.get("error")
        summary = result.get("quality_summary", {})
    except Exception as exc:  # noqa: BLE001 - preserve re-analysis evidence
        findings = []
        error = f"re-analysis failed: {exc}"
        summary = {}

    agent_errors = [*state.get("agent_errors", [])]
    if error:
        agent_errors.append({"agent": "code_quality_reanalysis", "error": error})
    return {
        "reanalysis_findings": findings,
        "reanalysis_summary": summary,
        "agent_errors": agent_errors,
        "workflow_trace": [*state.get("workflow_trace", []), "Re-analysis completed"],
        "stage_history": [*state.get("stage_history", []), {
            "stage": "reanalyze", "status": "partial" if error else "completed",
            "finding_count": len(findings),
        }],
    }


async def compare_results(state: WorkflowState) -> dict:
    """Compare original findings and post-repair quality findings."""
    before = {finding.get("issue") for finding in state.get("findings", [])}
    after = {finding.get("issue") for finding in state.get("reanalysis_findings", [])}
    changed_files = [
        path for path, content in (state.get("repaired_code") or {}).items()
        if content != state.get("project_files", {}).get(path)
    ]
    comparison = {
        "findings_before": len(before),
        "findings_after": len(after),
        "resolved_issues": sorted(before - after),
        "remaining_issues": sorted(after),
        "changed_files": changed_files,
        "improved": len(after) < len(before),
    }
    return {
        "comparison": comparison,
        "repair_attempts": [
            *state.get("repair_attempts", [])[:-1],
            {
                **state.get("repair_attempts", [])[-1],
                "findings_before": len(state.get("findings", [])),
                "findings_after": len(state.get("reanalysis_findings", [])),
                "quality_improved": comparison["improved"],
                "final_outcome": "improved" if comparison["improved"] else "needs_review",
            },
        ] if state.get("repair_attempts") else [],
        "workflow_trace": [*state.get("workflow_trace", []), "Before and after results compared"],
        "stage_history": [*state.get("stage_history", []), {
            "stage": "compare", "status": "completed", "improved": comparison["improved"]
        }],
    }


async def bump_retry(state: WorkflowState) -> dict:
    return {"retry_count": state.get("retry_count", 0) + 1}


async def finalize(state: WorkflowState) -> dict:
    """Builds the report returned to the frontend, whether validation
    ultimately passed or the retry budget was exhausted."""
    checks = _analysis_checks(state.get("project_context"))
    stage_history = list(state.get("stage_history", []))
    if checks is not None:
        reported_stages = {item.get("stage") for item in stage_history}
        skipped_stages = []
        if not checks["automated_repair"] and "repair" not in reported_stages:
            skipped_stages.append({"stage": "repair", "status": "skipped"})
        if not checks["final_validation"] and "validate" not in reported_stages:
            skipped_stages.append({"stage": "validate", "status": "skipped"})
        if not checks["automated_repair"]:
            if "reanalyze" not in reported_stages:
                skipped_stages.append({"stage": "reanalyze", "status": "skipped"})
            if "compare" not in reported_stages:
                skipped_stages.append({"stage": "compare", "status": "skipped"})
        stage_history.extend(skipped_stages)
    stage_history.append({"stage": "finalize", "status": "completed"})
    report_state = {**state, "stage_history": stage_history}
    return {
        "final_code": state.get("repaired_code") or state.get("project_files", {}),
        "workflow_trace": [*state.get("workflow_trace", []), "Workflow report finalized"],
        "final_report": build_report(report_state),
        "stage_history": stage_history,
    }


def should_retry(state: WorkflowState) -> str:
    """Conditional-edge function: routes to 'finalize' on pass, back to
    'repair' on fail (up to max_retries), otherwise 'finalize' with a
    failed status so the graph always terminates."""
    if state.get("validation_status") == "passed":
        return "finalize"
    checks = _analysis_checks(state.get("project_context"))
    if checks is not None and not checks["automated_repair"]:
        return "finalize"
    sandbox_result = state.get("sandbox_result", {})
    validation_results = state.get("validation_results", {})
    if sandbox_result and not sandbox_result.get("executed"):
        return "finalize"
    if validation_results.get("error"):
        return "finalize"
    if state.get("retry_count", 0) >= settings.max_retries:
        return "finalize"
    return "retry"
