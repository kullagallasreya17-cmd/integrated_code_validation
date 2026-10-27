import asyncio
import json

import pytest
from pydantic import ValidationError

from app.models import Finding, RepairRequest
from app.services import repair_engine
from app.main import app
from fastapi.testclient import TestClient


def test_repair_file_returns_unchanged_code_without_findings():
    repair, unresolved = asyncio.run(repair_engine.repair_file("main.py", "print(1)\n", []))

    assert repair.changed is False
    assert repair.regenerated_code == "print(1)\n"
    assert unresolved == []


def test_repair_endpoint_returns_project_level_repair_response():
    response = TestClient(app).post("/repair", json={
        "project_id": "repair-contract-check",
        "files": [{"path": "main.py", "content": "print(1)\n"}],
        "findings": [],
    })

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["repairs"][0]["path"] == "main.py"
    assert response.json()["repairs"][0]["changed"] is False


def test_repair_file_accepts_validated_candidate(monkeypatch):
    async def generated_response(prompt: str) -> str:
        assert "resolved_finding_indexes" in prompt
        return json.dumps({
            "code": "def add(a, b):\n    return a + b\n",
            "explanation": "Use addition instead of subtraction.",
            "resolved_finding_indexes": [0],
        })

    monkeypatch.setattr(repair_engine, "generate_code", generated_response)
    monkeypatch.setattr(repair_engine, "validate_repair", lambda *_args: (True, "validated"))
    finding = Finding(file="main.py", line=2, type="logic", message="Wrong operator")

    repair, unresolved = asyncio.run(repair_engine.repair_file(
        "main.py", "def add(a, b):\n    return a - b\n", [finding]
    ))

    assert repair.changed is True
    assert repair.regenerated_code == "def add(a, b):\n    return a + b\n"
    assert unresolved == []


def test_repair_file_rejects_candidate_that_fails_validation(monkeypatch):
    async def generated_response(_prompt: str) -> str:
        return json.dumps({"code": "def add(:\n", "resolved_finding_indexes": [0]})

    monkeypatch.setattr(repair_engine, "generate_code", generated_response)
    monkeypatch.setattr(repair_engine, "validate_repair", lambda *_args: (False, "invalid syntax"))
    finding = Finding(file="main.py", line=1, message="Syntax issue")

    repair, unresolved = asyncio.run(repair_engine.repair_file("main.py", "def add(): pass\n", [finding]))

    assert repair.changed is False
    assert repair.regenerated_code == "def add(): pass\n"
    assert "rejected" in repair.explanation
    assert unresolved == [finding]


@pytest.mark.parametrize("path", ["../main.py", "/tmp/main.py", "C:/temp/main.py", "notes.txt"])
def test_repair_request_rejects_unsafe_or_non_python_paths(path):
    with pytest.raises(ValidationError):
        RepairRequest(files=[{"path": path, "content": "print(1)"}])