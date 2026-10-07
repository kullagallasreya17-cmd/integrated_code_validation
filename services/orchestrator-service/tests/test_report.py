from app.reporting.report_builder import build_report


def test_selected_quality_gate_failure_cannot_report_validation_pass():
	report = build_report({
		"project_id": "quality-failure",
		"validation_status": "passed",
		"project_context": {"analysis_checks": {
			"code_quality": True,
			"security": False,
			"bug_resource": False,
			"complexity": True,
			"automated_repair": False,
			"final_validation": True,
		}},
		"quality_summary": {"quality_gate_status": "FAIL"},
		"agent_errors": [{"agent": "code_quality", "error": "pylint: failed"}],
	})

	assert report["validation_status"] == "failed"
	assert report["workflow_status"] != "SUCCESS"


def test_unselected_quality_failure_does_not_override_selected_validation():
	report = build_report({
		"project_id": "quality-disabled",
		"validation_status": "passed",
		"project_context": {"analysis_checks": {
			"code_quality": False,
			"security": False,
			"bug_resource": False,
			"complexity": False,
			"automated_repair": False,
			"final_validation": True,
		}},
		"quality_summary": {"quality_gate_status": "FAIL"},
		"agent_errors": [{"agent": "code_quality", "error": "ruff: unavailable"}],
	})

	assert report["validation_status"] == "passed"


def test_selected_quality_without_complete_tool_evidence_cannot_report_pass():
	report = build_report({
		"project_id": "missing-quality-evidence",
		"validation_status": "passed",
		"project_context": {"analysis_checks": {
			"code_quality": True,
			"security": False,
			"bug_resource": False,
			"complexity": False,
			"automated_repair": False,
			"final_validation": True,
		}},
		"tools": ["ruff"],
		"quality_summary": {
			"quality_gate_status": "PASS",
			"tool_runs": [{"tool": "ruff", "status": "unavailable"}],
		},
	})

	assert report["validation_status"] == "failed"
	assert report["workflow_status"] != "SUCCESS"
