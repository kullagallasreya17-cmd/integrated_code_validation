from pydantic import ValidationError
import pytest

from app.main import AnalyzeRequest, ProjectFile, analyze, health


def request_for(code: str) -> AnalyzeRequest:
    return AnalyzeRequest(
        project_id="bug-resource-test",
        files=[ProjectFile(path="main.py", content=code)],
    )


def test_health_reports_bug_resource_service():
    assert health() == {"status": "healthy", "service": "bug-resource-service"}


def test_reports_mutable_defaults_swallowed_exceptions_and_file_risks():
    response = analyze(request_for(
        "def process(items=[]):\n"
        "    try:\n"
        "        source = open('data.txt')\n"
        "        return source.readlines()\n"
        "    except Exception:\n"
        "        pass\n"
    ))

    assert response.agent == "bug_resource"
    assert response.findings_count == len(response.findings)
    assert {finding.issue for finding in response.findings} == {"BUG001", "BUG002", "RES001", "RES002"}
    assert {finding.category for finding in response.findings} == {"bug", "resource"}
    assert all(finding.file == "main.py" for finding in response.findings)


def test_context_managed_bounded_read_has_no_resource_findings():
    response = analyze(request_for(
        "def read_header(path):\n"
        "    with open(path) as source:\n"
        "        return source.read(128)\n"
    ))

    assert response.findings == []


def test_syntax_error_is_returned_as_a_bug_finding():
    response = analyze(request_for("def broken(:\n    pass\n"))

    assert response.findings_count == 1
    assert response.findings[0].issue == "BUG000"
    assert response.findings[0].line_number == 1


def test_file_paths_must_be_relative_python_files():
    with pytest.raises(ValidationError):
        ProjectFile(path="../outside.py", content="print('no')")

    with pytest.raises(ValidationError):
        ProjectFile(path="notes.txt", content="not python")