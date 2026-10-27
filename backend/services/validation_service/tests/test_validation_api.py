import subprocess

from fastapi.testclient import TestClient

from app import validator
from app import main
from app.main import app


client = TestClient(app)


def test_missing_flake8_is_not_reported_as_valid(monkeypatch):
    def missing_analyzer(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["python", "-m", "flake8"],
            returncode=2,
            stdout="",
            stderr="No module named flake8",
        )

    monkeypatch.setattr(validator.subprocess, "run", missing_analyzer)
    response = client.post("/validate", json={
        "code": "print('valid syntax')\n",
        "filename": "main.py",
    })

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["findings"][0]["code"] == "VALIDATOR_ERROR"
    assert "No module named flake8" in response.json()["findings"][0]["message"]


def test_flake8_timeout_is_a_validation_failure(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="flake8", timeout=20)

    monkeypatch.setattr(validator.subprocess, "run", timeout)
    response = client.post("/validate", json={
        "code": "print('valid syntax')\n",
        "filename": "main.py",
    })

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["findings"][0]["code"] == "VALIDATOR_TIMEOUT"


def test_style_findings_are_review_not_runtime_failure(monkeypatch):
    monkeypatch.setattr(main, "validate_code", lambda *_args: ([{
        "type": "CodeQuality",
        "severity": "LOW",
        "file": "main.py",
        "line": 1,
        "message": "Unused import",
        "code": "F401",
        "recommendation": "Remove the unused import.",
    }], {"lines_of_code": 1, "functions": 0, "classes": 0, "imports": 1, "max_function_length": 0, "max_nesting_depth": 0}))

    response = client.post("/validate", json={"code": "import os", "filename": "main.py"})

    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["status"] == "needs_review"
    assert response.json()["needs_review"] is True


def test_valid_python_passes_syntax_check(monkeypatch):
    monkeypatch.setattr(validator, "run_flake8", lambda *_args: [])

    response = client.post("/validate", json={
        "code": "def greet(name):\n    return f'hello {name}'\n",
        "filename": "main.py",
    })

    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["status"] == "passed"


def test_e305_is_reported_as_review_finding(monkeypatch):
    monkeypatch.setattr(validator, "run_flake8", lambda *_args: [{
        "type": "CodeQuality",
        "severity": "LOW",
        "file": "main.py",
        "line": 4,
        "column": 1,
        "message": "E305: expected 2 blank lines after class or function definition",
        "code": "E305",
        "recommendation": "Add the required blank lines after the definition.",
    }])

    response = client.post("/validate", json={
        "code": "def greet():\n    return 'hello'\nprint(greet())\n",
        "filename": "main.py",
    })

    assert response.status_code == 200
    assert response.json()["status"] == "needs_review"
    assert response.json()["findings"][0]["code"] == "E305"
    assert response.json()["findings"][0]["line"] == 4


def test_missing_colon_fails_syntax_with_diagnostic():
    response = client.post("/validate", json={
        "code": "if True\n    print('broken')\n",
        "filename": "main.py",
    })

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert response.json()["status"] == "failed"
    assert response.json()["findings"][0]["code"] == "SYNTAX"
    assert response.json()["findings"][0]["line"] == 1
    assert "expected ':'" in response.json()["findings"][0]["message"]