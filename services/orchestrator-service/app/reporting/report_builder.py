from app.aggregation.finding_aggregator import summarize
from app.config import settings


CHECK_NAMES = ("code_quality", "security", "bug_resource", "complexity", "automated_repair", "final_validation")


def _analysis_checks(state: dict) -> dict[str, bool]:
    raw_checks = (state.get("project_context") or {}).get("analysis_checks")
    if not isinstance(raw_checks, dict):
        return dict.fromkeys(CHECK_NAMES, True)
    return {name: bool(raw_checks.get(name, True)) for name in CHECK_NAMES}


def _quality_evidence_failed(state: dict, checks: dict[str, bool]) -> bool:
    if not (checks["code_quality"] or checks["complexity"]):
        return False
    quality_summary = state.get("quality_summary") or {}
    quality_gate = quality_summary.get("quality_gate_status") or quality_summary.get("quality_gate", {}).get("status")
    required_tools = state.get("tools") or quality_summary.get("selected_tools") or []
    completed_tools = {
        run.get("tool")
        for run in quality_summary.get("tool_runs", [])
        if isinstance(run, dict) and run.get("status") == "completed"
    }
    return quality_gate != "PASS" or not required_tools or not set(required_tools).issubset(completed_tools)


def _agent_error_is_selected(error: dict, checks: dict[str, bool], quality_selected: bool) -> bool:
    agent = error.get("agent")
    selected_agents = {
        "code_quality": quality_selected,
        "security": checks["security"],
        "bug_resource": checks["bug_resource"],
        "repair": checks["automated_repair"],
        "code_quality_reanalysis": checks["automated_repair"],
        "sandbox": checks["final_validation"],
        "validation": checks["final_validation"],
    }
    return selected_agents.get(agent, False)


def _effective_validation_status(state: dict) -> str:
    status = state.get("validation_status", "unknown")
    if status != "passed":
        return status

    checks = _analysis_checks(state)
    quality_selected = checks["code_quality"] or checks["complexity"]
    if _quality_evidence_failed(state, checks):
        return "failed"
    if any(_agent_error_is_selected(error, checks, quality_selected) for error in state.get("agent_errors", [])):
        return "failed"
    return status


def _workflow_status(state: dict) -> str:
    validation_status = _effective_validation_status(state)
    retry_count = state.get("retry_count", 0)
    agent_failures = state.get("agent_errors", [])
    quality_gate = (state.get("quality_summary") or {}).get("quality_gate_status") or (state.get("quality_summary") or {}).get("quality_gate", {}).get("status")

    if validation_status == "passed":
        return "SUCCESS"
    if retry_count >= settings.max_retries:
        return "MAX_REPAIR_ATTEMPTS_REACHED"
    if agent_failures:
        return "AGENT_FAILURE" if quality_gate != "FAIL" else "PARTIAL_RESULT"
    if validation_status == "failed":
        return "FAILED"
    if quality_gate == "FAIL":
        return "REVIEW_REQUIRED"
    return "PARTIAL_RESULT"


def build_report(state: dict) -> dict:
    findings = state.get("findings", [])
    quality_summary = state.get("quality_summary", {})
    validation_status = _effective_validation_status(state)
    report_state = {**state, "validation_status": validation_status}
    workflow_summary = {
        "workflow_status": _workflow_status(report_state),
        "total_findings": len(findings),
        "findings_by_severity": summarize(findings).get("by_severity", {}),
        "quality_score": quality_summary.get("overall_score", quality_summary.get("quality_score", 0)),
        "quality_gate": quality_summary.get("quality_gate_status") or quality_summary.get("quality_gate", {}).get("status", "UNKNOWN"),
        "repair_attempts": state.get("repair_attempts", []),
        "validation_result": state.get("validation_results", {}),
        "agent_failures": state.get("agent_errors", []),
        "workflow_duration_seconds": state.get("workflow_duration_seconds"),
    }
    return {
        "project_id": state["project_id"],
        "analysis_id": state.get("analysis_id", state["project_id"]),
        "validation_status": validation_status,
        "workflow_status": workflow_summary["workflow_status"],
        "retry_count": state.get("retry_count", 0),
        "max_retries": settings.max_retries,
        "findings_summary": summarize(findings),
        "findings": findings,
        "quality_summary": quality_summary,
        "workflow_summary": workflow_summary,
        "prioritized_findings": state.get("prioritized_findings", findings),
        "explanations": state.get("explanations", []),
        "code_report": state.get("code_report", {}),
        "recommendation_report": state.get("recommendation_report", {}),
        "ai_recommendations_status": state.get("ai_recommendations_status", {"status": "disabled"}),
        "reanalysis_findings": state.get("reanalysis_findings", []),
        "reanalysis_summary": state.get("reanalysis_summary", {}),
        "comparison": state.get("comparison", {}),
        "validation_results": state.get("validation_results", {}),
        "sandbox_result": state.get("sandbox_result", {}),
        "agent_errors": state.get("agent_errors", []),
        "stage_history": state.get("stage_history", []),
        "workflow_trace": state.get("workflow_trace", [item.get("stage") for item in state.get("stage_history", [])]),
        "analysis_checks": state.get("project_context", {}).get("analysis_checks"),
        "code_structure": state.get("code_structure", {}),
        "repair_attempts": state.get("repair_attempts", []),
        "final_code": state.get("repaired_code") or state.get("project_files", {}),
        "recommendations": [
            finding.get("recommendation")
            for finding in findings
            if finding.get("recommendation")
        ],
    }