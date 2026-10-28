"""
Individual LangGraph nodes. Each node takes the WorkflowState, does one
job, and returns a partial dict that LangGraph merges back into state.

Nodes only talk to other services through the `app/services/*_client.py`
clients — never by importing another team member's code directly.
"""
import asyncio
from collections import Counter
import hashlib
import json
import logging
import re
from datetime import datetime, timezone

import httpx

from app.graph.state import WorkflowState
from app.services import (
    security_client,
    quality_client,
    bug_resource_client,
    repair_client,
    report_recommendation_client,
    sandbox_client,
    validation_client,
)
from app.aggregation.finding_aggregator import aggregate
from app.config import settings
from app.analysis.python_structure import inspect_python_files
from app.reporting.report_builder import build_report
from shared.languages import detect_language, source_files

logger = logging.getLogger(__name__)


def understand_project(state: WorkflowState) -> dict:
    """Light-weight project intake: just confirms we have files and sets
    initial counters. Kept separate from `analyze` so it's easy to later
    add real project-understanding (dependency graph, language detection)
    without touching the analysis fan-out logic."""
    files = state.get("project_files", {})
    checks = _analysis_checks(state.get("project_context"))
    language = detect_language(list(source_files(files)))
    structure = inspect_python_files(_python_files(files))
    stage = {"stage": "understand", "status": "completed", "file_count": len(files)}
    return {
        "retry_count": 0,
        "repair_attempt": 0,
        "tools": state.get("tools") if language == "python" else None,
        "validation_status": "not_run" if checks is not None and not checks["final_validation"] else "pending",
        "code_structure": structure,
        "analysis_id": state.get("analysis_id") or state.get("run_id") or state.get("project_id"),
        "agent_errors": [],
        "stage_history": [stage],
        "workflow_trace": ["Workflow started", "Project understanding completed"],
        "error": None if files else "No project files supplied",
    }


def _analysis_agent_flags(checks: dict | None) -> tuple[bool, bool, bool]:
    security_enabled = checks is None or checks["security"]
    quality_enabled = checks is None or checks["code_quality"] or checks["complexity"]
    resource_enabled = (checks is None or checks["bug_resource"]) and bool(settings.bug_resource_service_url)
    return security_enabled, quality_enabled, resource_enabled


def _python_files(files: dict[str, str]) -> dict[str, str]:
    return {path: content for path, content in files.items() if path.lower().endswith(".py")}


async def _collect_analysis_responses(
    project_id: str,
    files: dict[str, str],
    context: dict,
    tools: list[str] | None,
    security_enabled: bool,
    quality_enabled: bool,
    resource_enabled: bool,
) -> dict[str, dict]:
    calls = []
    agents = []
    language = detect_language(list(source_files(files)))
    quality_tools = tools if language == "python" else None
    if security_enabled:
        agents.append("security")
        calls.append(security_client.analyze(project_id, files, context))
    if quality_enabled:
        agents.append("code_quality")
        calls.append(quality_client.analyze(project_id, files, context, quality_tools))
    if resource_enabled:
        agents.append("bug_resource")
        calls.append(bug_resource_client.analyze(project_id, source_files(files), context))

    results = await asyncio.gather(*calls, return_exceptions=True)
    responses = {}
    for agent, result in zip(agents, results):
        if isinstance(result, Exception):
            responses[agent] = {"findings": [], "error": f"{agent} failed: {result}"}
        else:
            responses[agent] = result
    return responses


def _collect_analysis_errors(responses: dict[str, dict]) -> list[dict[str, str]]:
    return [
        {"agent": agent, "error": result["error"]}
        for agent, result in responses.items()
        if result.get("error")
    ]


def _analysis_agent_statuses(
    security_enabled: bool,
    quality_enabled: bool,
    resource_enabled: bool,
    agent_errors: list[dict[str, str]],
) -> dict[str, str]:
    statuses = {
        "security": "skipped" if not security_enabled else "completed",
        "quality": "skipped" if not quality_enabled else "completed",
        "bug_resource": "skipped" if not resource_enabled else "completed",
    }
    for error in agent_errors:
        agent = "quality" if error["agent"] == "code_quality" else error["agent"]
        if agent in statuses:
            statuses[agent] = "failed"
    return statuses


def _log_analysis_endpoints(
    state: WorkflowState,
    stage: str,
    flags: tuple[bool, bool, bool],
    file_count: int,
) -> None:
    security_enabled, quality_enabled, resource_enabled = flags
    endpoints: list[str] = []
    if security_enabled:
        endpoints.append("security:/scan")
    if quality_enabled:
        endpoints.append("code-quality:/analyze")
    if resource_enabled:
        endpoints.append("bug-resource:/analyze")
    workflow_id = state.get("run_id") or state.get("analysis_id") or state.get("project_id")
    logger.info(
        "workflow_endpoint_calls run_id=%s node=%s endpoints=%s file_count=%s",
        workflow_id,
        stage,
        ",".join(endpoints) if endpoints else "none",
        file_count,
        extra={
            "workflow_run_id": workflow_id,
            "workflow_node": stage,
            "service_endpoints": endpoints,
        },
    )


async def analyze(state: WorkflowState) -> dict:
    """Fan out to enabled analysis agents and store their raw findings."""
    files = state.get("project_files", {})
    analysis_files = files
    context = state.get("project_context", {})
    project_id = state["project_id"]
    tools = state.get("tools")
    flags = _analysis_agent_flags(_analysis_checks(context))
    quality_enabled = flags[1]
    _log_analysis_endpoints(state, "analyze", flags, len(source_files(analysis_files)))
    responses = await _collect_analysis_responses(
        project_id, analysis_files, context, tools, *flags
    )
    security_res = responses.get("security", {"findings": []})
    quality_res = responses.get("code_quality", {"findings": []})
    resource_res = responses.get("bug_resource", {"findings": []})
    agent_errors = _collect_analysis_errors(responses)
    agent_statuses = _analysis_agent_statuses(*flags, agent_errors)

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
        "ai_report_recommendations": bool(checks.get("ai_report_recommendations", False)),
    }


def aggregate_findings(state: WorkflowState) -> dict:
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


def explain_and_prioritize(state: WorkflowState) -> dict:
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


async def report_and_recommend(state: WorkflowState) -> dict:
    checks = _analysis_checks(state.get("project_context"))
    code_report = {}
    recommendation_report = {}
    if checks is None or not checks["ai_report_recommendations"]:
        status = {"status": "disabled"}
        stage_status = "skipped"
    else:
        try:
            result = await report_recommendation_client.analyze(source_files(state.get("project_files", {})))
            code_report = result.get("code_report", {})
            recommendation_report = result.get("recommendation_report", {})
            if result.get("status") == "skipped":
                status = {"status": "skipped", "message": result.get("message", "Agent is not configured.")}
                stage_status = "skipped"
            else:
                status = {"status": "completed", "provider": result.get("provider")}
                stage_status = "completed"
        except Exception as exc:  # noqa: BLE001 - optional AI reporting must not fail analysis
            if isinstance(exc, httpx.TimeoutException):
                message = "AI report/recommendation generation timed out while waiting for Ollama."
            elif isinstance(exc, httpx.HTTPStatusError):
                detail = ""
                try:
                    detail = str(exc.response.json().get("detail") or "")
                except ValueError:
                    pass
                message = f"AI report service returned HTTP {exc.response.status_code}."
                if detail:
                    message = f"{message} {detail}"
            else:
                message = f"AI report/recommendation generation failed ({type(exc).__name__})."
            status = {
                "status": "failed",
                "message": message,
            }
            stage_status = "failed"

    return {
        "code_report": code_report,
        "recommendation_report": recommendation_report,
        "ai_recommendations_status": status,
        "workflow_trace": [*state.get("workflow_trace", []), "AI report and recommendation stage completed"],
        "stage_history": [*state.get("stage_history", []), {
            "stage": "report_recommend",
            "status": stage_status,
            **({"message": status["message"]} if status.get("message") else {}),
        }],
    }


def _skipped_stages(checks: dict | None, stage_history: list[dict]) -> list[dict[str, str]]:
    if checks is None:
        return []
    reported_stages = {item.get("stage") for item in stage_history}
    skipped = []
    if not checks["automated_repair"] and "repair" not in reported_stages:
        skipped.append({"stage": "repair", "status": "skipped"})
    if not checks["final_validation"] and "validate" not in reported_stages:
        skipped.append({"stage": "validate", "status": "skipped"})
    if not checks["automated_repair"]:
        if "reanalyze" not in reported_stages:
            skipped.append({"stage": "reanalyze", "status": "skipped"})
        if "compare" not in reported_stages:
            skipped.append({"stage": "compare", "status": "skipped"})
    return skipped


async def repair(state: WorkflowState) -> dict:
    """Calls the Fix & Regeneration service with the current findings."""
    project_files = state.get("repaired_code") or state.get("project_files", {})
    files = source_files(project_files)
    language = detect_language(list(files))
    attempt = state.get("repair_attempt", 0) + 1
    input_findings = (
        state.get("reanalysis_findings", [])
        if state.get("repair_attempt", 0) > 0
        else state.get("findings", [])
    )
    previous_attempts = state.get("repair_attempts", [])
    previous_attempt = previous_attempts[-1] if previous_attempts else {}
    repair_feedback = ""
    previous_error = previous_attempt.get("error") or ""
    previous_error = previous_error or previous_attempt.get("candidate_rejection_reason") or ""
    regression_reasons = previous_attempt.get("regression_reasons", [])
    if regression_reasons:
        previous_error = "\n".join([previous_error, *regression_reasons]).strip()
    previous_unresolved = previous_attempt.get("unresolved_findings", [])
    if previous_error or previous_unresolved or regression_reasons:
        feedback_details = []
        for detail in previous_attempt.get("repair_details", []):
            explanation = detail.get("explanation")
            if (
                explanation
                and explanation != previous_error
                and not previous_error.startswith("Repair rejected:")
            ):
                feedback_details.append(f"{detail.get('path', 'unknown file')}: {explanation}")
            candidate = detail.get("candidate_code")
            if candidate:
                feedback_details.append(
                    f"Rejected candidate for {detail.get('path', 'unknown file')} "
                    f"(do not repeat it):\n{candidate}"
                )
        for path, candidate in previous_attempt.get("candidate_files", {}).items():
            if candidate:
                feedback_details.append(
                    f"Candidate for {path} failed verification; correct the diagnostics below:\n{candidate}"
                )
        unresolved_findings = [
            (
                f"{finding.get('file', 'unknown file')}:{finding.get('line') or '?'} "
                f"{finding.get('rule_id') or finding.get('issue') or finding.get('type')}: "
                f"{finding.get('message') or finding.get('description') or 'Finding remains unresolved.'} "
                f"Recommendation: {finding.get('recommendation') or 'Apply a minimal targeted fix.'}"
            )
            for finding in previous_unresolved
        ]
        repair_feedback = "\n".join([previous_error, *feedback_details, *unresolved_findings])

    try:
        repair_arguments = (
            state["project_id"], files, input_findings, repair_feedback
        )
        logger.info(
            "workflow_endpoint_call run_id=%s node=repair endpoint=repair:/repair language=%s file_count=%s finding_count=%s",
            state.get("run_id") or state.get("analysis_id") or state["project_id"],
            language or "unknown",
            len(files),
            len(input_findings),
            extra={
                "workflow_run_id": state.get("run_id") or state.get("analysis_id") or state["project_id"],
                "service_endpoint": "repair:/repair",
            },
        )
        result = await (
            repair_client.repair(*repair_arguments)
            if language == "python"
            else repair_client.repair(*repair_arguments, language)
        )
    except Exception as exc:  # noqa: BLE001 - convert downstream failure to state
        logger.exception(
            "workflow_endpoint_exception run_id=%s node=repair endpoint=repair:/repair",
            state.get("run_id") or state.get("analysis_id") or state["project_id"],
            extra={
                "workflow_run_id": state.get("run_id") or state.get("analysis_id") or state["project_id"],
                "service_endpoint": "repair:/repair",
            },
        )
        result = {"repaired_files": [], "error": f"repair failed: {exc}"}
    repaired = {**project_files, **{f["path"]: f["content"] for f in result.get("repaired_files", [])}}

    repair_error = result.get("error")
    repair_status = result.get(
        "repair_status",
        {"completed": "needs_review", "partial": "needs_review", "failed": "failed"}.get(
            result.get("status"), "needs_review"
        ),
    )
    agent_errors = [*state.get("agent_errors", [])]
    if repair_error and repair_status not in {"needs_review", "not_run"}:
        agent_errors.append({"agent": "repair", "error": repair_error})
    repaired_files = repaired or project_files
    changed_files = [
        path for path in files
        if repaired_files.get(path) != project_files.get(path)
    ]
    if repair_status == "failed":
        repair_stage_status = "failed"
    elif repair_status == "partial":
        repair_stage_status = "partial"
    elif repair_status == "needs_review":
        repair_stage_status = "needs_review"
    elif repair_status == "not_run":
        repair_stage_status = "not_run"
    else:
        repair_stage_status = "completed"
    candidate_fingerprint = hashlib.sha256(
        json.dumps(repaired_files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    attempt_record = {
        "iteration": attempt,
        "mode": result.get("mode", "targeted"),
        "service_status": result.get("status", "unknown"),
        "repair_status": repair_status,
        "input_findings": input_findings,
        "input_files": {path: files[path] for path in changed_files},
        "candidate_files": {path: repaired_files[path] for path in changed_files},
        "candidate_fingerprint": candidate_fingerprint,
        "verification_status": result.get("repair_status", "needs_review"),
        "skipped_checks": result.get("skipped_checks", []),
        "rejected_candidates": [
            {"path": detail.get("path"), "code": detail.get("candidate_code")}
            for detail in result.get("repair_details", [])
            if detail.get("candidate_code") is not None
            and detail.get("explanation", "").startswith("Repair rejected:")
        ],
        "changed_files": changed_files,
        "outcome": repair_status,
        "unresolved_findings": result.get("unresolved_findings", []),
        "repair_details": result.get("repair_details", []),
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
            "stage": "repair",
            "status": repair_stage_status,
            "attempt": attempt,
        }],
    }


SANDBOX_BLOCKED_STATUSES = {"dependency_missing", "project_incomplete", "unsupported_project", "unavailable"}


def _validation_outcome(sandbox_result: dict, validation_result: dict) -> str:
    if validation_result.get("status") == "error" or validation_result.get("error"):
        return "error"
    if (
        sandbox_result.get("status") == "unavailable"
        or (sandbox_result.get("error") and not sandbox_result.get("executed"))
    ):
        return "error"
    sandbox_passed = sandbox_result.get("passed", sandbox_result.get("exit_code") == 0)
    if validation_result.get("status") in {"blocked", "inconclusive"}:
        return validation_result["status"]
    if sandbox_result.get("status") in SANDBOX_BLOCKED_STATUSES or not sandbox_result.get("executed"):
        return "blocked"
    if not sandbox_passed or not validation_result.get("passed"):
        return "failed"
    return validation_result.get("status", "passed")


def _record_validation_error(errors: list[dict], agent: str, detail: str) -> None:
    if not any(item.get("agent") == agent and item.get("error") == detail for item in errors):
        errors.append({"agent": agent, "error": detail})


def _validation_findings_detail(validation_result: dict) -> str:
    finding = next(iter(validation_result.get("findings", [])), {})
    return finding.get("description") or finding.get("issue") or "Validation checks reported blocking findings."


def _mark_repair_attempts(
    attempts: list[dict],
    validation_status: str,
    files: dict[str, str],
    reanalysis_findings: list[dict],
    quality_summary: dict,
    sandbox_result: dict,
    validation_results: dict,
) -> list[dict]:
    if not attempts or attempts[-1].get("outcome") in {"failed", "error"}:
        return attempts
    outcome = "validated"
    if validation_status == "needs_review":
        outcome = "needs_review"
    elif validation_status != "passed":
        outcome = "validation_failed"
    attempts[-1] = {
        **attempts[-1],
        "outcome": outcome,
        "validation_status": validation_status,
        **({
            "verified_files": files,
            "verified_findings": reanalysis_findings,
            "verified_quality_summary": quality_summary,
            "verified_sandbox_result": sandbox_result,
            "verified_validation_results": validation_results,
        } if validation_status == "passed" else {}),
    }
    return attempts


async def validate(state: WorkflowState) -> dict:
    """Run isolated execution and static validation, keeping their outcomes distinct."""
    files = state.get("repaired_code") or state.get("project_files", {})
    project_id = state["project_id"]
    workflow_id = state.get("run_id") or state.get("analysis_id") or project_id
    source_paths = source_files(files)
    language = detect_language(list(source_paths))
    sandbox_result = None
    if language == "python":
        try:
            sandbox_stdin = (state.get("project_context") or {}).get("sandbox_stdin", "")
            logger.info(
                "workflow_endpoint_call run_id=%s node=validate endpoint=sandbox:/execute language=%s file_count=%s",
                workflow_id,
                language,
                len(source_paths),
                extra={"workflow_run_id": workflow_id, "service_endpoint": "sandbox:/execute"},
            )
            sandbox_result = await sandbox_client.execute(project_id, files, sandbox_stdin)
        except Exception as exc:  # noqa: BLE001 - preserve the sandbox failure in the report
            logger.exception(
                "workflow_endpoint_exception run_id=%s node=validate endpoint=sandbox:/execute",
                workflow_id,
                extra={"workflow_run_id": workflow_id, "service_endpoint": "sandbox:/execute"},
            )
            sandbox_result = {"status": "unavailable", "executed": False, "passed": False, "error": f"sandbox failed: {exc}"}
    try:
        validation_arguments = (project_id, files, state.get("findings", []))
        logger.info(
            "workflow_endpoint_call run_id=%s node=validate endpoint=validation:/validate language=%s file_count=%s",
            workflow_id,
            language or "unknown",
            len(source_paths),
            extra={"workflow_run_id": workflow_id, "service_endpoint": "validation:/validate"},
        )
        validation_result = await validation_client.validate(*validation_arguments)
        if language != "python":
            sandbox_result = validation_result.pop("sandbox_result", None)
            if not isinstance(sandbox_result, dict):
                sandbox_result = {
                    "status": "unavailable",
                    "executed": False,
                    "passed": False,
                    "error": validation_result.get("error") or "Validation service did not return sandbox execution details.",
                }
    except Exception as exc:  # noqa: BLE001 - preserve the validation failure in the report
        logger.exception(
            "workflow_endpoint_exception run_id=%s node=validate endpoint=validation:/validate",
            workflow_id,
            extra={"workflow_run_id": workflow_id, "service_endpoint": "validation:/validate"},
        )
        validation_result = {"passed": False, "status": "error", "error": f"validation failed: {exc}"}
        if sandbox_result is None:
            sandbox_result = {
                "status": "unavailable",
                "executed": False,
                "passed": False,
                "error": f"validation failed: {exc}",
            }

    if sandbox_result is None:
        sandbox_result = {"status": "unavailable", "executed": False, "passed": False}
    validation_status = _validation_outcome(sandbox_result, validation_result)
    logger.info(
        "workflow_validation_result run_id=%s status=%s sandbox_status=%s sandbox_exit_code=%s validator_status=%s validator_passed=%s",
        workflow_id,
        validation_status,
        sandbox_result.get("status"),
        sandbox_result.get("exit_code"),
        validation_result.get("status"),
        validation_result.get("passed"),
        extra={
        "workflow_run_id": workflow_id,
        "validation_status": validation_status,
        "sandbox_status": sandbox_result.get("status"),
        "sandbox_exit_code": sandbox_result.get("exit_code"),
        "validator_status": validation_result.get("status"),
        },
    )
    if validation_result.get("error"):
        logger.error(
        "workflow_validation_error run_id=%s detail=%s",
        workflow_id,
        validation_result["error"],
        extra={"workflow_run_id": workflow_id, "validation_status": validation_status},
        )
    validation_results = {
        **validation_result,
        "validator_passed": validation_result.get("passed"),
        "validator_status": validation_result.get("status"),
        "passed": validation_status == "passed",
        "status": validation_status,
    }
    agent_errors = [*state.get("agent_errors", [])]
    if not sandbox_result.get("executed") or not sandbox_result.get("passed", sandbox_result.get("exit_code") == 0):
        _record_validation_error(agent_errors, "sandbox", sandbox_result.get("error", "Sandbox execution failed"))
    if validation_results.get("error"):
        _record_validation_error(agent_errors, "validation", validation_results["error"])
    elif validation_status == "failed":
        _record_validation_error(agent_errors, "validation", _validation_findings_detail(validation_results))

    repair_attempts = list(state.get("repair_attempts", []))
    selected_files = files
    selected_sandbox = sandbox_result
    selected_validation = validation_results
    selected_findings = state.get("reanalysis_findings", [])
    selected_summary = state.get("reanalysis_summary", {})
    selected_best_candidate = state.get("best_repair_candidate")
    rollback_reason = None
    if validation_status != "passed" and repair_attempts:
        sandbox_diagnostic = (
            sandbox_result.get("error")
            or sandbox_result.get("stderr")
            or sandbox_result.get("stdout")
        )
        rollback_reason = (
            validation_results.get("error")
            or sandbox_diagnostic
            or _validation_findings_detail(validation_results)
        )
        previous_verified = next(
            (
                attempt for attempt in reversed(repair_attempts[:-1])
                if attempt.get("validation_status") == "passed"
                and isinstance(attempt.get("verified_files"), dict)
            ),
            None,
        )
        if previous_verified:
            selected_files = previous_verified["verified_files"]
            selected_findings = previous_verified.get("verified_findings", state.get("findings", []))
            selected_summary = previous_verified.get("verified_quality_summary", state.get("quality_summary", {}))
            selected_sandbox = previous_verified.get("verified_sandbox_result", sandbox_result)
            selected_validation = previous_verified.get("verified_validation_results", validation_results)
            validation_status = "passed"
        else:
            selected_files = state.get("project_files", {})
            selected_findings = state.get("findings", [])
            selected_summary = state.get("quality_summary", {})
        selected_best_candidate = {
            "files": selected_files,
            "findings": selected_findings,
            "quality_summary": selected_summary,
            "finding_count": len(selected_findings),
            "quality_score": _quality_score(selected_summary),
            "comparison_available": True,
        }
        repair_attempts[-1] = {
            **repair_attempts[-1],
            "candidate_rejected": True,
            "candidate_rejection_reason": rollback_reason,
            "candidate_rollback": True,
        }
    repair_attempts = _mark_repair_attempts(
        repair_attempts,
        validation_status,
        selected_files,
        selected_findings,
        selected_summary,
        selected_sandbox,
        selected_validation,
    )
    if rollback_reason and repair_attempts:
        repair_attempts[-1] = {
            **repair_attempts[-1],
            "candidate_rejected": True,
            "candidate_rejection_reason": rollback_reason,
            "candidate_rollback": True,
        }
    return {
        "repaired_code": selected_files,
        "reanalysis_findings": selected_findings,
        "reanalysis_summary": selected_summary,
        "best_repair_candidate": selected_best_candidate,
        "sandbox_result": selected_sandbox,
        "validation_results": selected_validation,
        "validation_status": validation_status,
        "repair_attempts": repair_attempts,
        "agent_errors": agent_errors,
        "workflow_trace": [*state.get("workflow_trace", []), "Validation completed"],
        "stage_history": [*state.get("stage_history", []), {"stage": "validate", "status": validation_status}],
    }


async def reanalyze(state: WorkflowState) -> dict:
    """Re-run enabled analysis agents against the repair candidate."""
    files = state.get("repaired_code") or state.get("project_files", {})
    analysis_files = files
    context = state.get("project_context", {})
    flags = _analysis_agent_flags(_analysis_checks(context))
    _log_analysis_endpoints(state, "reanalyze", flags, len(source_files(analysis_files)))
    try:
        responses = await _collect_analysis_responses(
            state["project_id"], analysis_files, context, state.get("tools"), *flags
        )
    except Exception as exc:  # noqa: BLE001 - preserve re-analysis evidence
        message = f"re-analysis failed: {exc}"
        responses = {
            agent: {"findings": [], "error": message}
            for agent, enabled in zip(("security", "code_quality", "bug_resource"), flags)
            if enabled
        }

    agent_errors = [*state.get("agent_errors", [])]
    reanalysis_errors = _collect_analysis_errors(responses)
    agent_errors.extend(
        {"agent": f"{error['agent']}_reanalysis", "error": error["error"]}
        for error in reanalysis_errors
    )
    security_res = responses.get("security", {"findings": []})
    quality_res = responses.get("code_quality", {"findings": []})
    resource_res = responses.get("bug_resource", {"findings": []})
    findings = aggregate(
        security_res.get("findings", []),
        quality_res.get("findings", []),
        resource_res.get("findings", []),
    )
    quality_summary = quality_res.get("quality_summary", {})
    best_candidate = state.get("best_repair_candidate")
    if best_candidate is None:
        baseline_available = "findings" in state or "quality_summary" in state
        best_candidate = {
            "files": state.get("project_files", {}),
            "findings": state.get("findings", []),
            "quality_summary": state.get("quality_summary", {}),
            "finding_count": len(state.get("findings", [])),
            "quality_score": _quality_score(state.get("quality_summary", {})),
            "comparison_available": baseline_available,
        }

    candidate_score = _quality_score(quality_summary)
    regression_reasons = []
    skipped_quality_tools = _skipped_quality_tools(
        quality_summary,
        state.get("tools") or quality_summary.get("selected_tools"),
    )
    analysis_available = bool(any(flags)) and not reanalysis_errors and not skipped_quality_tools
    if analysis_available and best_candidate.get("comparison_available", True):
        if len(findings) > best_candidate["finding_count"]:
            regression_reasons.append(
                f"Candidate increased findings from {best_candidate['finding_count']} to {len(findings)}."
            )
        previous_serious_security = Counter(
            _finding_base_identity(finding)
            for finding in best_candidate.get("findings", [])
            if str(finding.get("category", "")).lower() == "security"
            and str(finding.get("severity", "")).lower() in {"critical", "high"}
        )
        current_serious_security = Counter(
            _finding_base_identity(finding)
            for finding in findings
            if str(finding.get("category", "")).lower() == "security"
            and str(finding.get("severity", "")).lower() in {"critical", "high"}
        )
        if any(
            count > previous_serious_security[identity]
            for identity, count in current_serious_security.items()
        ):
            regression_reasons.append(
                "Candidate introduced a new critical or high-severity security finding."
            )
        best_score = best_candidate.get("quality_score")
        if (
            best_score is not None
            and candidate_score is not None
            and candidate_score < best_score
        ):
            regression_reasons.append(
                f"Candidate lowered quality score from {best_score:g} to {candidate_score:g}."
            )
    elif reanalysis_errors:
        regression_reasons.append(
            "Candidate was not promoted because re-analysis did not complete successfully."
        )
    elif skipped_quality_tools:
        regression_reasons.append(
            "Candidate was not promoted because selected analyzers were unavailable: "
            + ", ".join(sorted(skipped_quality_tools))
            + "."
        )

    regression_rollback = bool(regression_reasons)
    if regression_rollback:
        selected_files = best_candidate["files"]
        selected_findings = best_candidate["findings"]
        selected_summary = best_candidate["quality_summary"]
    else:
        selected_files = files
        selected_findings = findings
        selected_summary = quality_summary
        if analysis_available:
            best_candidate = {
                "files": files,
                "findings": findings,
                "quality_summary": quality_summary,
                "finding_count": len(findings),
                "quality_score": candidate_score,
                "comparison_available": True,
            }

    repair_attempts = list(state.get("repair_attempts", []))
    if repair_attempts:
        repair_attempts[-1] = {
            **repair_attempts[-1],
            "regression_rollback": regression_rollback,
            "regression_reasons": regression_reasons,
            "candidate_rejected": regression_rollback,
            "candidate_rollback": regression_rollback,
            **({
                "candidate_rejection_reason": "; ".join(regression_reasons)
            } if regression_rollback else {}),
            "candidate_findings_after": len(findings),
            "candidate_quality_score": candidate_score,
            "candidate_findings": findings,
            "candidate_quality_summary": quality_summary,
        }
    agent_statuses = _analysis_agent_statuses(*flags, reanalysis_errors)
    reanalysis_status = (
        "skipped" if not any(flags)
        else "partial" if reanalysis_errors
        else "completed"
    )
    return {
        "repaired_code": selected_files,
        "reanalysis_findings": selected_findings,
        "reanalysis_summary": selected_summary,
        "best_repair_candidate": best_candidate,
        "repair_attempts": repair_attempts,
        "agent_errors": agent_errors,
        "workflow_trace": [*state.get("workflow_trace", []), "Re-analysis completed"],
        "stage_history": [*state.get("stage_history", []), {
            "stage": "reanalyze",
            "status": reanalysis_status,
            "finding_count": len(findings),
            "regression_rollback": regression_rollback,
            "regression_reasons": regression_reasons,
            "agent_errors": reanalysis_errors,
            "agents": agent_statuses,
        }],
    }


def _quality_score(summary: dict) -> int | float | None:
    for key in ("overall_score", "quality_score"):
        score = summary.get(key)
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            return score
    return None


def _skipped_quality_tools(summary: dict, selected_tools: list[str] | None = None) -> set[str]:
    selected = {str(tool).lower() for tool in selected_tools or []}
    return {
        str(run.get("tool") or "unknown analyzer")
        for run in summary.get("tool_runs", [])
        if isinstance(run, dict)
        and run.get("status") in {"skipped", "not_run", "unavailable", "unsupported"}
        and (not selected or str(run.get("tool") or "").lower() in selected)
    }


def _finding_agent(finding: dict) -> str:
    category = str(finding.get("category", "")).lower()
    tool = str(finding.get("tool", "")).lower()
    if category == "security" or tool in {"bandit", "semgrep", "gitleaks"}:
        return "security"
    if category in {"bug", "resource"} or "resource" in category:
        return "bug_resource"
    return "quality"


def _finding_identity(finding: dict) -> tuple:
    return (*_finding_base_identity(finding), " ".join(
        str(finding.get("description") or finding.get("message") or "").strip().lower().split()
    ))


def _finding_symbol(finding: dict) -> str | None:
    message = str(finding.get("description") or finding.get("message") or "")
    match = re.search(r"""['"`‘’“”]([A-Za-z_$][\w$]*)['"`‘’“”]""", message)
    return match.group(1).lower() if match else None


def _dedupe_findings(findings: list[dict]) -> list[dict]:
    unique = []
    seen = set()
    for finding in findings:
        key = (
            *_finding_identity(finding),
            finding.get("line_number", finding.get("line")),
            " ".join(str(finding.get("evidence") or "").strip().lower().split()),
        )
        if key not in seen:
            unique.append(finding)
            seen.add(key)
    return unique


def _finding_base_identity(finding: dict) -> tuple:
    issue = str(finding.get("issue") or "").strip().lower()
    evidence = str(finding.get("evidence") or "").strip()
    rule = re.search(r"\b[A-Z]\d{3,5}\b", str(finding.get("issue") or ""))
    if not rule:
        rule = re.search(r"\b[A-Z]\d{3,5}\b", evidence)
    identity = rule.group(0).lower() if rule else issue
    symbol = _finding_symbol(finding)
    if issue in {"language_analyzer", "language_analyzer_failed"}:
        identity = (
            issue,
            symbol or " ".join(
                str(finding.get("description") or finding.get("message") or "").strip().lower().split()
            ),
        )
    elif symbol:
        identity = (identity, "symbol", symbol)
    return (
        str(finding.get("category") or "").lower(),
        str(finding.get("tool") or "").lower(),
        str(finding.get("file") or "").replace("\\", "/").lower(),
        identity,
    )


def compare_results(state: WorkflowState) -> dict:
    """Compare findings without collapsing repeated rules or masking failed agents."""
    before = _dedupe_findings(state.get("findings", []))
    after = _dedupe_findings(state.get("reanalysis_findings", []))
    reanalysis_stage = next(
        (stage for stage in reversed(state.get("stage_history", [])) if stage.get("stage") == "reanalyze"),
        {},
    )
    analysis_stage = next(
        (stage for stage in reversed(state.get("stage_history", [])) if stage.get("stage") == "analyze"),
        {},
    )
    failed_agents = {
        agent
        for stage in (analysis_stage, reanalysis_stage)
        for agent, status in stage.get("agents", {}).items()
        if status in {"failed", "blocked", "unavailable", "unsupported"}
    }
    skipped_agents = {
        agent
        for stage in (analysis_stage, reanalysis_stage)
        for agent, status in stage.get("agents", {}).items()
        if status in {"skipped", "not_run"}
    }
    skipped_tools = set()
    for summary in (state.get("quality_summary") or {}, state.get("reanalysis_summary") or {}):
        skipped_tools.update(_skipped_quality_tools(
            summary,
            state.get("tools") or summary.get("selected_tools"),
        ))
    skipped_tools.update(
        str(check)
        for attempt in state.get("repair_attempts", [])
        for check in attempt.get("skipped_checks", [])
    )
    unverified_before = [finding for finding in before if _finding_agent(finding) in failed_agents]
    unverified_after = [finding for finding in after if _finding_agent(finding) in failed_agents]
    skipped_before = [finding for finding in before if _finding_agent(finding) in skipped_agents]
    skipped_after = [finding for finding in after if _finding_agent(finding) in skipped_agents]
    unavailable_agents = failed_agents | skipped_agents
    comparable_before = [finding for finding in before if _finding_agent(finding) not in unavailable_agents]
    comparable_after = [finding for finding in after if _finding_agent(finding) not in unavailable_agents]

    exact_after: dict[tuple, list[int]] = {}
    base_before: dict[tuple, list[int]] = {}
    base_after: dict[tuple, list[int]] = {}
    for index, finding in enumerate(comparable_after):
        exact_after.setdefault(_finding_identity(finding), []).append(index)
        base_after.setdefault(_finding_base_identity(finding), []).append(index)
    for index, finding in enumerate(comparable_before):
        base_before.setdefault(_finding_base_identity(finding), []).append(index)

    matched_before: set[int] = set()
    matched_after: set[int] = set()
    for before_index, finding in enumerate(comparable_before):
        matches = exact_after.get(_finding_identity(finding), [])
        after_index = next((index for index in matches if index not in matched_after), None)
        if after_index is not None:
            matched_before.add(before_index)
            matched_after.add(after_index)

    for identity, before_indexes in base_before.items():
        unmatched_before = [index for index in before_indexes if index not in matched_before]
        unmatched_after = [
            index for index in base_after.get(identity, [])
            if index not in matched_after
        ]
        if (
            len(before_indexes) == len(base_after.get(identity, [])) == 1
            and len(unmatched_before) == len(unmatched_after) == 1
        ):
            matched_before.add(unmatched_before[0])
            matched_after.add(unmatched_after[0])

    unchanged = [
        finding for index, finding in enumerate(comparable_before)
        if index in matched_before
    ]
    resolved = [
        finding for index, finding in enumerate(comparable_before)
        if index not in matched_before
    ]
    introduced = [
        finding for index, finding in enumerate(comparable_after)
        if index not in matched_after
    ]
    comparison_complete = (
        not failed_agents
        and not skipped_before
        and not skipped_after
        and not skipped_tools
        and analysis_stage.get("status") == "completed"
        and reanalysis_stage.get("status") == "completed"
    )
    comparison_status = (
        "complete" if comparison_complete
        else "not_run" if reanalysis_stage.get("status") == "skipped"
        else "partial"
    )
    unverified_findings = unverified_after or unverified_before
    skipped_findings = skipped_after or skipped_before
    changed_files = [
        path for path, content in (state.get("repaired_code") or {}).items()
        if content != state.get("project_files", {}).get(path)
    ]
    comparison = {
        "status": comparison_status,
        "findings_before": len(before),
        "findings_after": len(after) if comparison_complete else None,
        "resolved_count": len(resolved),
        "unchanged_count": len(unchanged),
        "new_count": len(introduced),
        "unverified_count": max(len(unverified_before), len(unverified_after)),
        "skipped_checks": sorted([
            *(
                agent for agent in skipped_agents
                if any(_finding_agent(finding) == agent for finding in [*before, *after])
            ),
            *skipped_tools,
        ]),
        "skipped_findings": skipped_findings,
        "remaining_original_count": len(unchanged) + len(unverified_before) + len(skipped_before),
        "unverified_before_count": len(unverified_before),
        "unverified_after_count": len(unverified_after),
        "resolved_findings": resolved,
        "unchanged_findings": unchanged,
        "new_findings": introduced,
        "unverified_findings": [*unverified_before, *unverified_after],
        "remaining_findings": [*unchanged, *introduced, *unverified_findings, *skipped_findings],
        "resolved_issues": sorted({finding.get("issue", "Unknown issue") for finding in resolved}),
        "remaining_issues": sorted({
            finding.get("issue", "Unknown issue")
        for finding in [*unchanged, *introduced, *unverified_findings, *skipped_findings]
        }),
        "unverified_before_findings": unverified_before,
        "unverified_after_findings": unverified_after,
        "skipped_before_findings": skipped_before,
        "skipped_after_findings": skipped_after,
        "changed_files": changed_files,
        "improved": comparison_complete and len(after) < len(before),
    }
    quality_summary = state.get("quality_summary") or {}
    reanalysis_summary = state.get("reanalysis_summary") or {}
    before_score = quality_summary.get("overall_score", quality_summary.get("quality_score"))
    after_score = reanalysis_summary.get("overall_score", reanalysis_summary.get("quality_score"))
    if before_score is not None:
        comparison["quality_score_before"] = before_score
    if comparison_complete and after_score is not None:
        comparison["quality_score_after"] = after_score
    final_outcome = "improved" if comparison["improved"] else "needs_review"
    attempts = list(state.get("repair_attempts", []))
    if attempts:
        if not comparison_complete:
            final_status = "needs_review"
        elif not unchanged and not introduced:
            final_status = "success"
        elif resolved:
            final_status = "partial"
        elif attempts[-1].get("candidate_rollback"):
            final_status = "failed"
        elif not attempts[-1].get("changed_files"):
            final_status = "failed"
        else:
            final_status = "needs_review"
        attempts[-1] = {
            **attempts[-1],
            "repair_status": final_status,
            "verification_status": "verified" if comparison_complete else "needs_review",
            "verified_resolved_findings": resolved,
            "remaining_findings": [*unchanged, *unverified_before, *skipped_before],
            "introduced_findings": introduced,
            "unverified_findings": unverified_findings,
            "skipped_findings": skipped_findings,
            "skipped_checks": comparison["skipped_checks"],
        }
    return {
        "comparison": comparison,
        "repair_attempts": [
            *attempts[:-1],
            {
                **attempts[-1],
                "findings_before": len(before),
                "findings_after": len(after) if comparison_complete else None,
                "quality_improved": comparison["improved"],
                "final_outcome": final_outcome,
            },
        ] if attempts else [],
        "workflow_trace": [*state.get("workflow_trace", []), "Before and after results compared"],
        "stage_history": [*state.get("stage_history", []), {
            "stage": "compare", "status": "completed", "improved": comparison["improved"]
        }],
    }


def bump_retry(state: WorkflowState) -> dict:
    return {"retry_count": state.get("retry_count", 0) + 1}


def finalize(state: WorkflowState) -> dict:
    """Builds the report returned to the frontend, whether validation
    ultimately passed or the retry budget was exhausted."""
    checks = _analysis_checks(state.get("project_context"))
    stage_history = list(state.get("stage_history", []))
    stage_history.extend(_skipped_stages(checks, stage_history))
    stage_history.append({"stage": "finalize", "status": "completed"})
    report_state = {**state, "stage_history": stage_history}
    final_report = build_report(report_state)
    return {
        "final_code": state.get("repaired_code") or state.get("project_files", {}),
        "validation_status": final_report["validation_status"],
        "workflow_trace": [*state.get("workflow_trace", []), "Workflow report finalized"],
        "final_report": final_report,
        "stage_history": stage_history,
    }


def should_retry(state: WorkflowState) -> str:
    """Conditional-edge function: routes to 'finalize' on pass, back to
    'repair' on fail (up to max_retries), otherwise 'finalize' with a
    failed status so the graph always terminates."""
    validation_status = state.get("validation_status")
    if validation_status in {"blocked", "inconclusive"}:
        return "finalize"
    checks = _analysis_checks(state.get("project_context"))
    if checks is not None and not checks["automated_repair"]:
        return "finalize"
    repair_attempts = state.get("repair_attempts", [])
    last_attempt = repair_attempts[-1] if repair_attempts else {}
    last_fingerprint = last_attempt.get("candidate_fingerprint")
    if last_fingerprint and any(
        attempt.get("candidate_fingerprint") == last_fingerprint
        for attempt in repair_attempts[:-1]
    ):
        return "finalize"
    if validation_status in {"passed", "needs_review"}:
        reanalysis_stage = next(
            (stage for stage in reversed(state.get("stage_history", [])) if stage.get("stage") == "reanalyze"),
            {},
        )
        previous_findings = last_attempt.get("input_findings")
        remaining_findings = state.get("reanalysis_findings", [])
        repair_error = last_attempt.get("error") or ""
        repair_needs_revision = repair_error.startswith((
            "Repair rejected:",
            "Repair made no source changes",
            "Model response",
            "Ollama returned a response that was not valid JSON.",
        ))
        if (
            validation_status == "passed"
            and repair_needs_revision
            and remaining_findings
            and state.get("retry_count", 0) < settings.max_retries
        ):
            return "retry"
        no_finding_progress = (
            len(repair_attempts) > 1
            and previous_findings is not None
            and Counter(_finding_identity(finding) for finding in previous_findings)
            == Counter(_finding_identity(finding) for finding in remaining_findings)
        )
        if (
            remaining_findings
            and reanalysis_stage.get("status") == "completed"
            and last_attempt.get("changed_files")
            and not no_finding_progress
            and state.get("retry_count", 0) < settings.max_retries
        ):
            return "retry"
        if validation_status == "passed":
            return "finalize"
    repair_error = last_attempt.get("error") or ""
    repair_needs_revision = repair_error.startswith((
        "Repair rejected:",
        "Repair made no source changes",
        "Model response",
        "Ollama returned a response that was not valid JSON.",
    ))
    if validation_status == "needs_review" and not repair_needs_revision:
        return "finalize"
    sandbox_result = state.get("sandbox_result", {})
    validation_results = state.get("validation_results", {})
    if sandbox_result and not sandbox_result.get("executed"):
        return "finalize"
    if validation_results.get("error"):
        return "finalize"
    if repair_attempts:
        if last_attempt.get("error") and not last_attempt.get("changed_files"):
            if not repair_needs_revision:
                return "finalize"
    if state.get("retry_count", 0) >= settings.max_retries:
        return "finalize"
    return "retry"
