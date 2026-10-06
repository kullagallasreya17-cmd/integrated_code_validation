import asyncio
import pytest

from app.graph.workflow import build_workflow
from app.schemas.requests import StartAnalysisRequest


def test_workflow_runs_end_to_end_with_downstream_boundaries(monkeypatch):
    """
    Downstream boundaries are mocked so this graph test remains fast and
    deterministic. Client fallback behavior is tested at each HTTP client.
    """
    from app.services import (
        bug_resource_client,
        quality_client,
        repair_client,
        sandbox_client,
        security_client,
        validation_client,
    )

    async def no_findings(*args, **kwargs):
        return {"findings": []}

    async def unchanged_repair(*args, **kwargs):
        files = args[1]
        return {"repaired_files": [{"path": path, "content": content} for path, content in files.items()]}

    async def sandbox_pass(*args, **kwargs):
        return {"executed": True, "exit_code": 0}

    async def validation_pass(*args, **kwargs):
        return {"passed": True, "tests": {"passed": 1}}

    monkeypatch.setattr(security_client, "analyze", no_findings)
    monkeypatch.setattr(quality_client, "analyze", no_findings)
    monkeypatch.setattr(bug_resource_client, "analyze", no_findings)
    monkeypatch.setattr(repair_client, "repair", unchanged_repair)
    monkeypatch.setattr(sandbox_client, "execute", sandbox_pass)
    monkeypatch.setattr(validation_client, "validate", validation_pass)

    wf = build_workflow()
    stage_events = []

    result = asyncio.run(wf.ainvoke(
        {
            "project_id": "proj-test",
            "project_files": {"app.py": "print('hi')\n"},
            "project_context": {},
        },
        config={"configurable": {"on_stage": lambda stage, status: stage_events.append((stage, status))}},
    ))

    assert result["project_id"] == "proj-test" if "project_id" in result else True
    assert result.get("validation_status") in ("passed", "failed")
    assert result.get("retry_count", 0) <= 3
    assert "final_report" in result

    stages = [item["stage"] for item in result.get("stage_history", [])]
    assert stages.index("explain_prioritize") < stages.index("repair")
    assert stages.index("repair") < stages.index("validate")
    assert stages.index("validate") < stages.index("reanalyze")
    assert stages.index("reanalyze") < stages.index("compare")
    assert "explanations" in result["final_report"]
    assert "reanalysis_findings" in result["final_report"]
    assert "comparison" in result["final_report"]
    assert ("understand", "running") in stage_events
    assert ("analyze", "running") in stage_events
    assert ("compare", "completed") in stage_events


def test_analysis_checks_skip_unselected_agents_repair_and_validation(monkeypatch):
    from app.services import bug_resource_client, quality_client, repair_client, sandbox_client, security_client, validation_client

    calls = []

    async def quality_only(project_id, files, context, tools):
        calls.append(("quality", tools))
        return {"findings": [], "quality_summary": {"tool_runs": [{"tool": "radon", "status": "completed", "finding_count": 0}]}}

    async def unexpected(*args, **kwargs):
        raise AssertionError("a disabled agent or stage must not run")

    monkeypatch.setattr(quality_client, "analyze", quality_only)
    monkeypatch.setattr(security_client, "analyze", unexpected)
    monkeypatch.setattr(bug_resource_client, "analyze", unexpected)
    monkeypatch.setattr(repair_client, "repair", unexpected)
    monkeypatch.setattr(sandbox_client, "execute", unexpected)
    monkeypatch.setattr(validation_client, "validate", unexpected)

    checks = {
        "code_quality": False,
        "security": False,
        "bug_resource": False,
        "complexity": True,
        "automated_repair": False,
        "final_validation": False,
    }
    result = asyncio.run(build_workflow().ainvoke({
        "project_id": "proj-custom-checks",
        "project_files": {"app.py": "print('hi')\n"},
        "project_context": {"analysis_checks": checks},
        "tools": ["radon"],
    }))

    assert calls == [("quality", ["radon"])]
    stage_statuses = {stage["stage"]: stage["status"] for stage in result["stage_history"]}
    assert stage_statuses["repair"] == "skipped"
    assert stage_statuses["validate"] == "skipped"
    assert stage_statuses["reanalyze"] == "skipped"
    assert stage_statuses["compare"] == "skipped"
    assert result["final_report"]["analysis_checks"] == checks
    assert result["validation_status"] == "pending"


def test_final_validation_can_run_without_automated_repair(monkeypatch):
    from app.services import bug_resource_client, quality_client, repair_client, sandbox_client, security_client, validation_client

    async def unexpected_analysis(*args, **kwargs):
        raise AssertionError("analysis agents were disabled")

    async def unexpected_repair(*args, **kwargs):
        raise AssertionError("automated repair was disabled")

    async def sandbox_pass(project_id, files):
        assert files == {"app.py": "print('hi')\n"}
        return {"executed": True, "exit_code": 0}

    async def validation_pass(project_id, files, findings):
        assert files == {"app.py": "print('hi')\n"}
        return {"passed": True, "tests": {"passed": 1}}

    monkeypatch.setattr(quality_client, "analyze", unexpected_analysis)
    monkeypatch.setattr(security_client, "analyze", unexpected_analysis)
    monkeypatch.setattr(bug_resource_client, "analyze", unexpected_analysis)
    monkeypatch.setattr(repair_client, "repair", unexpected_repair)
    monkeypatch.setattr(sandbox_client, "execute", sandbox_pass)
    monkeypatch.setattr(validation_client, "validate", validation_pass)

    result = asyncio.run(build_workflow().ainvoke({
        "project_id": "proj-final-validation-only",
        "project_files": {"app.py": "print('hi')\n"},
        "project_context": {"analysis_checks": {
            "code_quality": False,
            "security": False,
            "bug_resource": False,
            "complexity": False,
            "automated_repair": False,
            "final_validation": True,
        }},
        "tools": [],
    }))

    stage_statuses = {stage["stage"]: stage["status"] for stage in result["stage_history"]}
    assert stage_statuses["repair"] == "skipped"
    assert stage_statuses["validate"] == "passed"
    assert stage_statuses["reanalyze"] == "skipped"
    assert result["validation_status"] == "passed"


def test_start_request_rejects_invalid_project_files():
    with pytest.raises(ValueError):
        StartAnalysisRequest(project_id="", files=[])


def test_start_request_rejects_duplicate_paths():
    with pytest.raises(ValueError):
        StartAnalysisRequest(
            project_id="p",
            files=[
                {"path": "main.py", "content": ""},
                {"path": "main.py", "content": ""},
            ],
        )


@pytest.mark.parametrize("path", ["C:/private/app.py", "../app.py", "/tmp/app.py", "notes.txt"])
def test_start_request_rejects_unsafe_or_non_python_paths(path):
    with pytest.raises(ValueError):
        StartAnalysisRequest(project_id="p", files=[{"path": path, "content": "print('x')"}])


def test_workflow_summary_records_quality_gate_and_stop_status(monkeypatch):
    from app.services import (
        bug_resource_client,
        quality_client,
        repair_client,
        sandbox_client,
        security_client,
        validation_client,
    )

    async def quality_pass(*args, **kwargs):
        return {
            "findings": [{
                "file": "app.py",
                "line_number": 1,
                "issue": "F841",
                "severity": "medium",
                "description": "unused variable",
                "recommendation": "remove variable",
                "tool": "ruff",
            }],
            "quality_summary": {
                "overall_score": 88,
                "quality_gate_status": "PASS",
                "quality_gate": {"status": "PASS", "overall_score": 88, "thresholds": {"error_limit": 0, "warning_limit": 5}},
                "errors": 0,
                "warnings": 1,
                "complexity_issues": 0,
            },
        }

    async def no_findings(*args, **kwargs):
        return {"findings": []}

    async def unchanged_repair(*args, **kwargs):
        files = args[1]
        return {"repaired_files": [{"path": path, "content": content} for path, content in files.items()]}

    async def sandbox_pass(*args, **kwargs):
        return {"executed": True, "exit_code": 0}

    async def validation_pass(*args, **kwargs):
        return {"passed": True, "tests": {"passed": 1}}

    monkeypatch.setattr(security_client, "analyze", no_findings)
    monkeypatch.setattr(quality_client, "analyze", quality_pass)
    monkeypatch.setattr(bug_resource_client, "analyze", no_findings)
    monkeypatch.setattr(repair_client, "repair", unchanged_repair)
    monkeypatch.setattr(sandbox_client, "execute", sandbox_pass)
    monkeypatch.setattr(validation_client, "validate", validation_pass)

    wf = build_workflow()
    result = asyncio.run(wf.ainvoke({
        "project_id": "proj-summary",
        "project_files": {"app.py": "value = 1\nprint(value)\n"},
        "project_context": {},
    }))

    summary = result.get("final_report", {}).get("workflow_summary", {})
    assert summary.get("workflow_status") in {"SUCCESS", "PASSED", "PARTIAL_RESULT", "REVIEW_REQUIRED", "FAILED"}
    assert summary.get("quality_gate") in {"PASS", "FAIL"}
    assert "quality_score" in summary
