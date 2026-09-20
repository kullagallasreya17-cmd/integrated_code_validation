from app.aggregation.finding_aggregator import summarize
from app.config import settings


def build_report(state: dict) -> dict:
    findings = state.get("findings", [])
    return {
        "project_id": state["project_id"],
        "analysis_id": state.get("analysis_id", state["project_id"]),
        "validation_status": state.get("validation_status", "unknown"),
        "workflow_status": "completed" if state.get("validation_status") == "passed" else "failed",
        "retry_count": state.get("retry_count", 0),
        "max_retries": settings.max_retries,
        "findings_summary": summarize(findings),
        "findings": findings,
        "quality_summary": state.get("quality_summary", {}),
        "prioritized_findings": state.get("prioritized_findings", findings),
        "explanations": state.get("explanations", []),
        "reanalysis_findings": state.get("reanalysis_findings", []),
        "reanalysis_summary": state.get("reanalysis_summary", {}),
        "comparison": state.get("comparison", {}),
        "validation_results": state.get("validation_results", {}),
        "sandbox_result": state.get("sandbox_result", {}),
        "agent_errors": state.get("agent_errors", []),
        "stage_history": state.get("stage_history", []),
        "code_structure": state.get("code_structure", {}),
        "repair_attempts": state.get("repair_attempts", []),
        "final_code": state.get("repaired_code") or state.get("project_files", {}),
        "recommendations": [
            finding.get("recommendation")
            for finding in findings
            if finding.get("recommendation")
        ],
    }