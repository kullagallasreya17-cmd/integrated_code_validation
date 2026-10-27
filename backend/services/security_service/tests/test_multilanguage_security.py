import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main


CLIENT = TestClient(main.app)
LANGUAGE_PROFILES = [
    ("main.py", "p/python"),
    ("main.js", "p/javascript"),
    ("main.ts", "p/typescript"),
    ("Main.java", "p/java"),
    ("main.c", "p/c"),
    ("main.cpp", "p/cpp"),
    ("main.go", "p/golang"),
    ("Program.cs", "p/csharp"),
]


@pytest.mark.parametrize(("filename", "profile"), LANGUAGE_PROFILES)
def test_security_scan_accepts_supported_language_and_selects_semgrep_profile(
    monkeypatch, filename, profile
):
    calls = []

    monkeypatch.setattr(main, "run_bandit", lambda *_args: [])

    def fake_run(arguments, **_kwargs):
        calls.append(arguments)
        return SimpleNamespace(
            stdout=json.dumps({"results": []}),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(main.subprocess, "run", fake_run)
    response = CLIENT.post("/scan", json={"filename": filename, "code": "source"})

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert calls[0][:3] == ["semgrep", "--config", profile]


@pytest.mark.parametrize("filename", [filename for filename, _ in LANGUAGE_PROFILES])
def test_security_api_returns_results_for_each_supported_language(monkeypatch, filename):
    monkeypatch.setattr(main, "run_bandit", lambda *_args: [])
    monkeypatch.setattr(main, "run_semgrep", lambda *_args: [])
    monkeypatch.setattr(main, "run_gitleaks", lambda *_args: [])

    response = CLIENT.post("/scan", json={"filename": filename, "code": "source"})

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["total_findings"] == 0
