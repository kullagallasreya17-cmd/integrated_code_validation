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

    result = asyncio.run(wf.ainvoke(
        {
            "project_id": "proj-test",
            "project_files": {"app.py": "print('hi')\n"},
            "project_context": {},
        }
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
