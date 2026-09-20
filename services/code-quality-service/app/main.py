from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.analyzers.ruff_analyzer import run_ruff
from app.analyzers.pylint_analyzer import run_pylint
from app.analyzers.radon_analyzer import run_radon
from app.parsers.result_normalizer import normalize
from app.schemas.finding import AnalyzeRequest
from app.config import settings
from shared.schemas.finding import FindingsResponse

app = FastAPI(title="Code Quality Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _quality_summary(files: dict[str, str], findings: list) -> dict:
    by_tool = {"ruff": 0, "pylint": 0, "radon": 0}
    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    complex_functions = 0
    for finding in findings:
        tool = finding.tool or "unknown"
        if tool in by_tool:
            by_tool[tool] += 1
        severity = finding.severity.value if hasattr(finding.severity, "value") else finding.severity
        if severity in by_severity:
            by_severity[severity] += 1
        if finding.issue.startswith("COMPLEXITY"):
            complex_functions += 1

    return {
        "files_analyzed": len(files),
        "total_findings": len(findings),
        "errors": by_severity["critical"] + by_severity["high"],
        "warnings": by_severity["medium"],
        "info": by_severity["low"] + by_severity["info"],
        "complex_functions": complex_functions,
        "by_tool": by_tool,
        "by_severity": by_severity,
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}


@app.post("/analyze", response_model=FindingsResponse)
def analyze(request: AnalyzeRequest):
    """
    Runs the requested static-analysis tools (ruff, pylint, radon) over
    the submitted files, normalizes their output to the shared Finding
    contract, and returns it.

    This is the endpoint the Orchestrator's `quality_client.py` calls.
    """
    tools = request.tools or settings.default_tools
    files = {f.path: f.content for f in request.files}

    if not files:
        return FindingsResponse(
            project_id=request.project_id,
            agent="code_quality",
            findings=[],
            findings_count=0,
            error="No files supplied",
        )

    if len(files) > settings.max_files:
        return FindingsResponse(
            project_id=request.project_id,
            agent="code_quality",
            findings=[],
            findings_count=0,
            error=f"Too many files supplied; maximum is {settings.max_files}",
        )

    oversized = [
        path for path, content in files.items()
        if len(content.encode("utf-8")) > settings.max_file_size_bytes
    ]
    if oversized:
        return FindingsResponse(
            project_id=request.project_id,
            agent="code_quality",
            findings=[],
            findings_count=0,
            error=f"File exceeds size limit: {oversized[0]}",
        )

    raw_issues: list[dict] = []
    tool_errors: list[str] = []
    analyzers = {
        "ruff": run_ruff,
        "pylint": run_pylint,
        "radon": run_radon,
    }
    for tool in tools:
        try:
            raw_issues += analyzers[tool](files)
        except Exception as exc:  # noqa: BLE001 - preserve other tool results
            tool_errors.append(f"{tool}: {exc}")
            raw_issues.append(
                {
                    "source": tool,
                    "file": None,
                    "line_number": None,
                    "code": f"{tool.upper()}_FAILED",
                    "message": "Analyzer failed; review service logs for details",
                    "severity_hint": "low",
                }
            )

    findings = normalize(raw_issues)

    return FindingsResponse(
        project_id=request.project_id,
        agent="code_quality",
        findings=findings,
        findings_count=len(findings),
        error="; ".join(tool_errors) if tool_errors else None,
        quality_summary=_quality_summary(files, findings),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
