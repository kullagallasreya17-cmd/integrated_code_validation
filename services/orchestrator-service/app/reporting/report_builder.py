from app.aggregation.finding_aggregator import summarize
from app.config import settings


def _workflow_status(state: dict) -> str:
    validation_status = state.get("validation_status", "unknown")
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
    workflow_summary = {
        "workflow_status": _workflow_status(state),
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
        "validation_status": state.get("validation_status", "unknown"),
        "workflow_status": workflow_summary["workflow_status"],
        "retry_count": state.get("retry_count", 0),
        "max_retries": settings.max_retries,
        "findings_summary": summarize(findings),
        "findings": findings,
        "quality_summary": quality_summary,
        "workflow_summary": workflow_summary,
        "prioritized_findings": state.get("prioritized_findings", findings),
        "explanations": state.get("explanations", []),
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