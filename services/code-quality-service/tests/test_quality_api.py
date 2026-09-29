from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_analyze_returns_findings_response_shape():
    payload = {
        "project_id": "proj-1",
        "files": [{"path": "app.py", "content": "import os\n\ndef f():\n    pass\n"}],
        "tools": ["ruff"],
    }
    resp = client.post("/analyze", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == "proj-1"
    assert body["agent"] == "code_quality"
    assert "findings" in body
    assert "findings_count" in body


def test_analyze_with_no_files_errors_gracefully():
    payload = {"project_id": "proj-2", "files": []}
    resp = client.post("/analyze", json=payload)
    assert resp.status_code == 200
    assert resp.json()["error"] == "No files supplied"


def test_analyze_rejects_path_traversal():
    payload = {
        "project_id": "proj-3",
        "files": [{"path": "../app.py", "content": "print('unsafe')"}],
        "tools": ["ruff"],
    }
    resp = client.post("/analyze", json=payload)
    assert resp.status_code == 422


def test_analyze_rejects_duplicate_normalized_file_paths():
    payload = {
        "project_id": "duplicate-files",
        "files": [
            {"path": "src/app.py", "content": "first = True\n"},
            {"path": "src\\app.py", "content": "second = True\n"},
        ],
        "tools": ["ruff"],
    }
    response = client.post("/analyze", json=payload)

    assert response.status_code == 422


def test_analyze_rejects_unknown_tool():
    payload = {
        "project_id": "proj-4",
        "files": [{"path": "app.py", "content": "print('ok')"}],
        "tools": ["unknown"],
    }
    resp = client.post("/analyze", json=payload)
    assert resp.status_code == 422


def test_analyze_keeps_partial_results_when_one_tool_fails(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "run_ruff", lambda files: [{
        "source": "ruff",
        "file": "app.py",
        "line_number": 1,
        "code": "F401",
        "message": "unused import",
        "severity_hint": "medium",
    }])
    monkeypatch.setattr(main, "run_pylint", lambda files: (_ for _ in ()).throw(RuntimeError("boom")))

    payload = {
        "project_id": "proj-5",
        "files": [{"path": "app.py", "content": "import os\n"}],
        "tools": ["ruff", "pylint"],
    }
    resp = client.post("/analyze", json=payload)
    body = resp.json()
    assert resp.status_code == 200
    assert body["findings_count"] == 2
    assert body["error"] == "pylint: failed"
    assert body["quality_summary"]["tool_results"]["pylint"]["status"] == "failed"
    assert "boom" not in body["error"]


def test_analyze_marks_missing_analyzer_unavailable_without_losing_other_results(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "run_ruff", lambda files: [{
        "source": "ruff", "file": "app.py", "line_number": 1,
        "code": "F401", "message": "unused import", "severity_hint": "medium",
    }])
    monkeypatch.setattr(main, "run_pylint", lambda files: (_ for _ in ()).throw(FileNotFoundError("C:/private/path/pylint.exe")))

    response = client.post("/analyze", json={
        "project_id": "missing-pylint",
        "files": [{"path": "app.py", "content": "import os\n"}],
        "tools": ["ruff", "pylint"],
    })

    body = response.json()
    assert body["quality_summary"]["tool_results"]["ruff"]["status"] == "completed"
    assert body["quality_summary"]["tool_results"]["pylint"]["status"] == "unavailable"
    assert "C:/private/path" not in body["error"]


def test_analyze_fails_quality_gate_when_all_selected_tools_are_unavailable(monkeypatch):
    from app import main

    for tool in ("ruff", "pylint", "radon"):
        monkeypatch.setattr(
            main,
            f"run_{tool}",
            lambda files: (_ for _ in ()).throw(FileNotFoundError("analyzer missing")),
        )

    response = client.post("/analyze", json={
        "project_id": "no-analyzers",
        "files": [{"path": "app.py", "content": "value = 1\n"}],
        "tools": ["ruff", "pylint", "radon"],
    })

    summary = response.json()["quality_summary"]
    assert summary["quality_gate_status"] == "FAIL"
    assert summary["quality_gate"]["status"] == "FAIL"
    assert {item["tool"] for item in summary["quality_gate"]["blocking_tools"]} == {"ruff", "pylint", "radon"}


def test_analyze_returns_quality_summary(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "run_ruff", lambda files: [{
        "source": "ruff",
        "file": "app.py",
        "line_number": 1,
        "code": "F401",
        "message": "unused import",
        "severity_hint": "medium",
    }])
    response = client.post("/analyze", json={
        "project_id": "summary-test",
        "files": [{"path": "app.py", "content": "import os\n"}],
        "tools": ["ruff"],
    })

    summary = response.json()["quality_summary"]
    assert summary["files_analyzed"] == 1
    assert summary["total_findings"] == 1
    assert summary["by_tool"]["ruff"] == 1
    assert summary["by_severity"]["medium"] == 1
    assert summary["style_issues"] == 0
    assert summary["complexity_issues"] == 0
    assert summary["by_category"]["code_quality"] == 1


def test_analyze_summarizes_style_and_complexity_categories(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "run_ruff", lambda files: [{
        "source": "ruff", "file": "app.py", "line_number": 1,
        "code": "C0116", "message": "Missing function or method docstring", "severity_hint": "low",
    }])
    monkeypatch.setattr(main, "run_pylint", lambda files: [])
    monkeypatch.setattr(main, "run_radon", lambda files: [{
        "source": "radon", "file": "app.py", "line_number": 2,
        "code": "COMPLEXITY_D", "message": "'run' has cyclomatic complexity 22 (grade D)", "severity_hint": "medium",
    }])

    response = client.post("/analyze", json={
        "project_id": "category-summary",
        "files": [{"path": "app.py", "content": "def run():\n    return True\n"}],
    })

    summary = response.json()["quality_summary"]
    assert summary["style_issues"] == 1
    assert summary["complexity_issues"] == 1
    assert summary["by_category"]["code_quality"] == 2


def test_analyze_exposes_quality_gate_and_hotspots(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "run_ruff", lambda files: [{
        "source": "ruff",
        "file": "app.py",
        "line_number": 8,
        "code": "F841",
        "message": "local variable 'value' is assigned to but never used",
        "severity_hint": "medium",
    }])
    monkeypatch.setattr(main, "run_pylint", lambda files: [{
        "source": "pylint",
        "file": "app.py",
        "line_number": 8,
        "code": "W0612",
        "message": "Unused variable 'value'",
        "severity_hint": "medium",
    }])
    monkeypatch.setattr(main, "run_radon", lambda files: [{
        "source": "radon",
        "file": "app.py",
        "line_number": 5,
        "code": "COMPLEXITY_E",
        "message": "'process_payment' has cyclomatic complexity 27 (grade E)",
        "severity_hint": "high",
    }])

    response = client.post("/analyze", json={
        "project_id": "gate-test",
        "files": [{"path": "app.py", "content": "def process_payment(amount):\n    value = amount * 2\n    return value\n"}],
        "tools": ["ruff", "pylint", "radon"],
    })

    summary = response.json()["quality_summary"]
    assert summary["overall_score"] >= 0
    assert summary["quality_gate_status"] in {"PASS", "FAIL"}
    assert summary["quality_gate"]["status"] == summary["quality_gate_status"]
    assert "hotspots" in summary
    assert summary["hotspots"][0]["file"] == "app.py"
    assert "per_file" in summary
    assert "tool_results" in summary
    assert summary["tool_results"]["ruff"]["status"] == "completed"


def test_analyze_deduplicates_cross_tool_unused_variable(monkeypatch):
    from app import main

    issue = {
        "file": "app.py",
        "line_number": 3,
        "message": "unused variable 'value'",
        "severity_hint": "medium",
    }
    monkeypatch.setattr(main, "run_ruff", lambda files: [{**issue, "source": "ruff", "code": "F841"}])
    monkeypatch.setattr(main, "run_pylint", lambda files: [{**issue, "source": "pylint", "code": "W0612"}])

    response = client.post("/analyze", json={
        "project_id": "dedup-test",
        "files": [{"path": "app.py", "content": "def run():\n    value = 1\n"}],
        "tools": ["ruff", "pylint"],
    })

    findings = response.json()["findings"]
    assert len(findings) == 1
    assert findings[0]["detected_by_tools"] == ["ruff", "pylint"]
