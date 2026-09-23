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
    assert body["error"] == "pylint: boom"


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
