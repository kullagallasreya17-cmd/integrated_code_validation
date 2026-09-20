from app.reporting.report_builder import build_report
from app.graph.nodes import compare_results, explain_and_prioritize


def test_report_contains_findings_repair_history_and_recommendations():
    report = build_report({
        "project_id": "project-1",
        "validation_status": "failed",
        "findings": [{"severity": "high", "recommendation": "Fix it"}],
        "repair_attempts": [{"iteration": 1, "outcome": "failed"}],
        "validation_results": {"passed": False},
    })

    assert report["workflow_status"] == "failed"
    assert report["findings_summary"]["total"] == 1
    assert report["repair_attempts"][0]["iteration"] == 1
    assert report["recommendations"] == ["Fix it"]


def test_explain_and_prioritize_orders_high_severity_findings():
    result = __import__("asyncio").run(explain_and_prioritize({
        "findings": [
            {"finding_id": "low", "severity": "low", "description": "low"},
            {"finding_id": "critical", "severity": "critical", "description": "critical"},
        ],
        "stage_history": [],
    }))

    assert result["prioritized_findings"][0]["finding_id"] == "critical"
    assert result["explanations"][0]["priority"] == 1


def test_compare_results_reports_resolved_issues_and_changed_files():
    result = __import__("asyncio").run(compare_results({
        "findings": [{"issue": "F401"}, {"issue": "COMPLEXITY_C"}],
        "reanalysis_findings": [{"issue": "COMPLEXITY_C"}],
        "project_files": {"main.py": "old"},
        "repaired_code": {"main.py": "new"},
        "stage_history": [],
    }))

    assert result["comparison"]["resolved_issues"] == ["F401"]
    assert result["comparison"]["changed_files"] == ["main.py"]