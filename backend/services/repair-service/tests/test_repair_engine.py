import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx
from pydantic import ValidationError

from app.models import CodeFile, Finding, RepairRequest
from app.services import repair_engine
from app.services import validation_service
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


def test_repair_health_reports_missing_model_as_provider_unavailable(monkeypatch):
    async def missing_model():
        return False, "The configured Ollama model is not installed."

    monkeypatch.setattr("app.main.model_status", missing_model)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["provider_ready"] is False
    assert "not installed" in response.json()["provider_error"]


def test_repair_file_accepts_validated_candidate(monkeypatch):
    async def generated_response(prompt: str) -> str:
        assert "resolved_finding_ids" in prompt
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
    assert repair.resolved_finding_ids == ["finding-1"]
    assert unresolved == []


@pytest.mark.parametrize(
    "language,filename",
    [
        ("python", "main.py"),
        ("java", "Main.java"),
        ("javascript", "main.js"),
        ("typescript", "main.ts"),
        ("c", "main.c"),
        ("cpp", "main.cpp"),
        ("csharp", "main.cs"),
        ("go", "main.go"),
    ],
)
def test_repair_prompt_uses_the_submitted_language(monkeypatch, language, filename):
    async def generated_response(prompt: str) -> str:
        assert f"Language: {language}" in prompt
        return json.dumps({
            "code": "updated source\n",
            "explanation": "Applied the requested correction.",
            "resolved_finding_ids": ["finding-1"],
        })

    monkeypatch.setattr(repair_engine, "generate_code", generated_response)
    monkeypatch.setattr(repair_engine, "validate_repair", lambda *_args: (True, "validated"))
    finding = Finding(finding_id="finding-1", file=filename, message="Correct this issue")

    repair, unresolved = asyncio.run(repair_engine.repair_file(
        filename, "original source\n", [finding], language=language
    ))

    assert repair.changed is True
    assert repair.resolved_finding_ids == ["finding-1"]
    assert unresolved == []


def test_java_repair_prompt_includes_filename_and_compiler_constraints(monkeypatch):
    async def generated_response(prompt: str) -> str:
        assert "Language: java" in prompt
        assert "without Markdown code fences" in prompt
        assert "Since the submitted file path cannot be renamed" in prompt
        assert "remove the public modifier only when that is safe" in prompt
        assert "never rename the type to an invalid Java identifier" in prompt
        assert "every referenced Java identifier is declared, imported from the correct package, and in scope" in prompt
        return json.dumps({"code": "```java\nclass java_test { }\n```\n"})

    monkeypatch.setattr(repair_engine, "generate_code", generated_response)
    monkeypatch.setattr(repair_engine, "validate_repair", lambda *_args: (True, "validated"))
    finding = Finding(file="java_test.java", message="Fix the compilation errors")

    repair, _ = asyncio.run(repair_engine.repair_file(
        "java_test.java",
        "public class JavaTest { }\n",
        [finding],
        language="java",
    ))

    assert repair.changed is True
    assert repair.regenerated_code == "class java_test { }\n"


@pytest.mark.parametrize(
    ("language", "guidance"),
    [
        ("c", "Removing only the initializer can leave the unused-variable finding unresolved."),
        ("cpp", "Removing only the initializer can leave the unused-variable finding unresolved."),
        ("csharp", "diagnostic reports CS0219"),
    ],
)
def test_repair_prompt_includes_unused_local_guidance(monkeypatch, language, guidance):
    async def generated_response(prompt: str) -> str:
        assert guidance in prompt
        return json.dumps({"code": "updated source\n"})

    monkeypatch.setattr(repair_engine, "generate_code", generated_response)
    monkeypatch.setattr(repair_engine, "validate_repair", lambda *_args: (True, "validated"))
    finding = Finding(file="main.source", message="Unused local variable")

    repair, _ = asyncio.run(repair_engine.repair_file(
        "main.source",
        "original source\n",
        [finding],
        language=language,
    ))

    assert repair.changed is True


@pytest.mark.parametrize(
    "language,filename,original,candidate",
    [
        ("python", "main.py", "print('old')\n", "print('new')\n"),
        ("java", "Main.java", "class Main { }\n", "class Main { int value = 1; }\n"),
        ("javascript", "main.js", "console.log('old');\n", "console.log('new');\n"),
        ("typescript", "main.ts", "console.log('old');\n", "console.log('new');\n"),
        ("c", "main.c", "int main(void) { return 0; }\n", "int main(void) { return 1; }\n"),
        ("cpp", "main.cpp", "int main() { return 0; }\n", "int main() { return 1; }\n"),
        ("csharp", "main.cs", "class Main { }\n", "class Main { int value = 1; }\n"),
        ("go", "main.go", "package main\nfunc main() {}\n", "package main\nfunc main() { println(1) }\n"),
    ],
)
def test_repair_keeps_changed_candidate_when_model_omits_finding_ids(
    monkeypatch, language, filename, original, candidate
):
    async def generated_response(_prompt: str) -> str:
        return json.dumps({"code": candidate, "explanation": "Applied a targeted change."})

    monkeypatch.setattr(repair_engine, "generate_code", generated_response)
    monkeypatch.setattr(repair_engine, "validate_repair", lambda *_args: (True, "validated"))
    finding = Finding(finding_id="finding-1", file=filename, message="Fix this issue")

    repair, unresolved = asyncio.run(repair_engine.repair_file(
        filename, original, [finding], language=language
    ))

    assert repair.changed is True
    assert repair.regenerated_code == candidate
    assert repair.resolved_finding_ids == []
    assert unresolved == [finding]


def test_repair_project_returns_partial_candidate_when_model_omits_finding_ids(monkeypatch):
    async def generated_response(_prompt: str) -> str:
        return json.dumps({
            "code": "int main(void) { return 1; }\n",
            "explanation": "Changed the return value.",
        })

    monkeypatch.setattr(repair_engine, "generate_code", generated_response)
    monkeypatch.setattr(repair_engine, "validate_repair", lambda *_args: (True, "validated"))
    finding = Finding(
        finding_id="finding-1",
        file="main.c",
        rule_id="LANGUAGE_ANALYZER",
        message="Correct the return value.",
    )
    request = RepairRequest(
        project_id="missing-repair-ids",
        language="c",
        files=[CodeFile(path="main.c", content="int main(void) { return 0; }\n")],
        findings=[finding],
    )

    result = asyncio.run(repair_engine.repair_project(request))

    assert result.status == "partial"
    assert result.outcome == "partially_applied"
    assert result.changed_files == ["main.c"]
    assert result.repairs[0].resolved_finding_ids == []
    assert result.unresolved_findings == [finding]


def test_repair_file_preserves_original_final_newline(monkeypatch):
    validated_candidates = []

    async def generated_response(_prompt: str) -> str:
        return json.dumps({"code": "print('fixed')", "resolved_finding_ids": ["finding-1"]})

    def validate_candidate(_original: str, candidate: str, _language: str, _path: str) -> tuple[bool, str]:
        validated_candidates.append(candidate)
        return True, "validated"

    monkeypatch.setattr(repair_engine, "generate_code", generated_response)
    monkeypatch.setattr(repair_engine, "validate_repair", validate_candidate)
    finding = Finding(finding_id="finding-1", file="main.py", message="Fix this issue")

    repair, unresolved = asyncio.run(repair_engine.repair_file(
        "main.py", "print('original')\n", [finding]
    ))

    assert validated_candidates == ["print('fixed')\n"]
    assert repair.regenerated_code == "print('fixed')\n"
    assert unresolved == []


def test_repair_file_adds_final_newline_to_candidate(monkeypatch):
    validated_candidates = []

    async def generated_response(_prompt: str) -> str:
        return json.dumps({"code": "print('fixed')", "resolved_finding_ids": ["finding-1"]})

    def validate_candidate(_original: str, candidate: str, _language: str, _path: str) -> tuple[bool, str]:
        validated_candidates.append(candidate)
        return True, "validated"

    monkeypatch.setattr(repair_engine, "generate_code", generated_response)
    monkeypatch.setattr(repair_engine, "validate_repair", validate_candidate)
    finding = Finding(finding_id="finding-1", file="main.py", message="Fix this issue")

    repair, unresolved = asyncio.run(repair_engine.repair_file(
        "main.py", "print('original')", [finding]
    ))

    assert validated_candidates == ["print('fixed')\n"]
    assert repair.regenerated_code == "print('fixed')\n"
    assert unresolved == []


@pytest.mark.parametrize("reference", [
    {"resolved_finding_indexes": [4]},
    {"resolved_finding_ids": ["not-a-real-finding"]},
    {"resolved_finding_ids": ["f-1"], "resolved_finding_indexes": [1]},
])
def test_repair_rejects_invalid_finding_references_without_changing_source(monkeypatch, reference):
    async def generated_response(_prompt: str) -> str:
        return json.dumps({"code": "print('candidate')\n", **reference})

    monkeypatch.setattr(repair_engine, "generate_code", generated_response)
    monkeypatch.setattr(repair_engine, "validate_repair", lambda *_args: (True, "checked"))
    original = "print('original')\n"
    finding = Finding(finding_id="f-1", file="main.py", message="Change output")

    repair, unresolved = asyncio.run(repair_engine.repair_file("main.py", original, [finding]))

    assert repair.changed is False
    assert repair.regenerated_code == original
    assert unresolved == [finding]
    assert "finding" in repair.explanation.lower()


def test_repair_no_change_keeps_finding_unresolved_and_reports_no_change(monkeypatch):
    async def generated_response(_prompt: str) -> str:
        return json.dumps({"code": "print('original')\n", "resolved_finding_ids": ["f-1"]})

    monkeypatch.setattr(repair_engine, "generate_code", generated_response)
    monkeypatch.setattr(repair_engine, "validate_repair", lambda *_args: (True, "checked"))
    request = RepairRequest(
        project_id="no-change",
        files=[CodeFile(path="main.py", content="print('original')\n")],
        findings=[Finding(finding_id="f-1", file="main.py", message="Change output")],
    )

    result = asyncio.run(repair_engine.repair_project(request))

    assert result.status == "failed"
    assert result.outcome == "no_change"
    assert result.changed_files == []
    assert result.repairs[0].changed is False
    assert result.unresolved_findings == request.findings


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
    assert repair.candidate_code == "def add(:\n"
    assert unresolved == [finding]


def test_repair_file_uses_ruff_when_model_candidate_leaves_unused_import(monkeypatch):
    original = 'import os\n\nprint("ready")\n'

    async def incomplete_response(_prompt: str) -> str:
        return json.dumps({
            "code": 'import os\nprint("ready")\n',
            "explanation": "Removed the unused import.",
            "resolved_finding_ids": [],
        })

    def autofix(command, **_kwargs):
        candidate = Path(command[-1])
        candidate.write_text(candidate.read_text(encoding="utf-8").replace("import os\n", ""), encoding="utf-8")
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    def diagnostics(code: str):
        if "import os" in code:
            return [{"code": "F401", "message": "`os` imported but unused"}]
        return []

    monkeypatch.setattr(repair_engine, "generate_code", incomplete_response)
    monkeypatch.setattr(repair_engine.shutil, "which", lambda _tool: "ruff")
    monkeypatch.setattr(repair_engine.subprocess, "run", autofix)
    monkeypatch.setattr(validation_service, "_ruff_diagnostics", diagnostics)
    finding = Finding(
        finding_id="unused-os-import",
        file="main.py",
        rule_id="F401",
        message="`os` imported but unused",
    )

    repair, unresolved = asyncio.run(repair_engine.repair_file("main.py", original, [finding]))

    assert repair.changed is True
    assert repair.regenerated_code == 'print("ready")\n'
    assert repair.resolved_finding_ids == ["unused-os-import"]
    assert unresolved == []


def test_repair_file_does_not_accept_model_claim_when_ruff_finding_remains(monkeypatch):
    async def generated_response(_prompt: str) -> str:
        return json.dumps({
            "code": 'import os\n\nprint("changed")\n',
            "resolved_finding_ids": ["unused-os-import"],
        })

    monkeypatch.setattr(repair_engine, "generate_code", generated_response)
    monkeypatch.setattr(
        validation_service,
        "_ruff_diagnostics",
        lambda _code: [{"code": "F401", "message": "`os` imported but unused"}],
    )
    finding = Finding(
        finding_id="unused-os-import",
        file="main.py",
        rule_id="F401",
        message="`os` imported but unused",
    )

    repair, unresolved = asyncio.run(
        repair_engine.repair_file("main.py", 'import os\n\nprint("ready")\n', [finding])
    )

    assert repair.changed is True
    assert repair.resolved_finding_ids == []
    assert unresolved == [finding]


def test_repair_file_reports_ollama_connection_failure(monkeypatch):
    async def unavailable(_prompt: str) -> str:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(repair_engine, "generate_code", unavailable)
    finding = Finding(file="main.py", line=1, message="Fix this issue")

    repair, unresolved = asyncio.run(repair_engine.repair_file("main.py", "print(1)\n", [finding]))

    assert repair.changed is False
    assert repair.explanation == "Could not connect to the configured Ollama endpoint."
    assert unresolved == [finding]


def test_ollama_repair_uses_extended_timeout(monkeypatch):
    from app.services import ollama_service

    captured = {}

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            captured["request"] = _kwargs["json"]

            class Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"response": "{}"}

            return Response()

    monkeypatch.setattr(ollama_service.httpx, "AsyncClient", FakeClient)
    asyncio.run(ollama_service.generate_code("repair prompt"))

    assert captured["timeout"] == 600
    assert captured["request"]["format"] == "json"


def test_validate_repair_allows_existing_rule_after_line_shift(monkeypatch):
    diagnostics = iter([
        [{"code": "W292", "message": "No newline at end of file", "location": {"row": 1, "column": 1}}],
        [{"code": "W292", "message": "No newline at end of file", "location": {"row": 2, "column": 1}}],
    ])
    monkeypatch.setattr(validation_service, "_ruff_diagnostics", lambda _code: next(diagnostics))

    valid, _ = validation_service.validate_repair(
        "print('hello')",
        '"""Greeting module."""\nprint("hello")',
    )

    assert valid is True


def test_validate_repair_rejects_additional_diagnostic_with_same_rule(monkeypatch):
    diagnostics = iter([
        [{"code": "W292", "message": "No newline at end of file", "location": {"row": 1, "column": 1}}],
        [
            {"code": "W292", "message": "No newline at end of file", "location": {"row": 1, "column": 1}},
            {"code": "W292", "message": "No newline at end of file", "location": {"row": 2, "column": 1}},
        ],
    ])
    monkeypatch.setattr(validation_service, "_ruff_diagnostics", lambda _code: next(diagnostics))

    valid, message = validation_service.validate_repair(
        "print('hello')",
        '"""Greeting module."""\nprint("hello")',
    )

    assert valid is False
    assert "W292 at line 2" in message


@pytest.mark.parametrize(
    ("language", "filename", "tool"),
    [
        ("javascript", "main.js", "node"),
        ("typescript", "main.ts", "tsc"),
        ("java", "Main.java", "javac"),
        ("c", "main.c", "gcc"),
        ("cpp", "main.cpp", "g++"),
        ("go", "main.go", "go"),
        ("csharp", "Program.cs", "mcs"),
    ],
)
def test_validate_repair_runs_language_compiler_for_non_python_candidates(
    monkeypatch, language, filename, tool
):
    observed = {}

    def run(command, **kwargs):
        observed["command"] = command
        observed["env"] = kwargs.get("env")
        source_path = Path(command[-1])
        assert source_path.name == filename
        assert source_path.read_text(encoding="utf-8") == "valid candidate\n"
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(validation_service.subprocess, "run", run)

    valid, message = validation_service.validate_repair(
        "original source\n",
        "valid candidate\n",
        language,
        filename,
    )

    assert valid is True
    assert tool in observed["command"][0]
    assert "validation passed" in message
    if language == "go":
        assert observed["env"]["GO111MODULE"] == "off"


@pytest.mark.parametrize(
    ("language", "filename"),
    [("go", "main.go"), ("csharp", "Program.cs")],
)
def test_validate_repair_rejects_compiler_errors_for_go_and_csharp(
    monkeypatch, language, filename
):
    monkeypatch.setattr(
        validation_service.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="compiler diagnostic: invalid source",
        ),
    )

    valid, message = validation_service.validate_repair(
        "original source\n",
        "invalid candidate\n",
        language,
        filename,
    )

    assert valid is False
    assert "compiler diagnostic" in message


def test_validate_repair_reports_missing_non_python_tool(monkeypatch):
    def missing_tool(*_args, **_kwargs):
        raise FileNotFoundError("compiler missing")

    monkeypatch.setattr(validation_service.subprocess, "run", missing_tool)

    valid, message = validation_service.validate_repair(
        "original\n",
        "candidate\n",
        "go",
        "main.go",
    )

    assert valid is False
    assert "Required validation tool is not installed: go" == message


@pytest.mark.parametrize("path", ["../main.py", "/tmp/main.py", "C:/temp/main.py", "notes.txt"])
def test_repair_request_rejects_unsafe_or_non_python_paths(path):
    with pytest.raises(ValidationError):
        RepairRequest(files=[{"path": path, "content": "print(1)"}])