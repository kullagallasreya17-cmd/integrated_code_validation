from time import perf_counter

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


def _build_gate_thresholds() -> dict:
    return {
        "error_limit": settings.quality_gate_error_threshold,
        "warning_limit": settings.quality_gate_warning_threshold,
        "complexity_limit": settings.quality_gate_complexity_threshold,
        "minimum_score": settings.quality_gate_min_score,
    }


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

    errors = by_severity["critical"] + by_severity["high"]
    warnings = by_severity["medium"]
    info = by_severity["low"] + by_severity["info"]
    overall_score = max(0, 100 - (errors * 12 + warnings * 5 + info * 1 + complex_functions * 4))
    thresholds = _build_gate_thresholds()
    gate_status = "PASS" if (
        errors <= thresholds["error_limit"]
        and warnings <= thresholds["warning_limit"]
        and complex_functions <= thresholds["complexity_limit"]
        and overall_score >= thresholds["minimum_score"]
    ) else "FAIL"

    return {
        "files_analyzed": len(files),
        "total_findings": len(findings),
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "complex_functions": complex_functions,
        "overall_score": overall_score,
        "quality_gate_status": gate_status,
        "quality_gate": {
            "status": gate_status,
            "overall_score": overall_score,
            "thresholds": thresholds,
        },
        "by_tool": by_tool,
        "by_severity": by_severity,
        "maintainability": {
            "complexity_issues": complex_functions,
            "high_risk_items": max(0, errors + warnings),
            "measured_values": {
                "errors": errors,
                "warnings": warnings,
                "info_items": info,
                "complex_functions": complex_functions,
            },
        },
    }


def _quality_score(summary: dict) -> int:
    """Return a transparent score for comparing runs, not a pass/fail verdict."""
    return int(summary.get("overall_score", 0))


def _detect_hotspots(raw_issues: list[dict]) -> list[dict]:
    hotspots: list[dict] = []
    for issue in raw_issues:
        code = issue.get("code") or ""
        if not code.startswith("COMPLEXITY"):
            continue
        complexity = 0
        label = code.replace("COMPLEXITY_", "")
        complexity_map = {"A": 5, "B": 10, "C": 15, "D": 20, "E": 27, "F": 40}
        complexity = complexity_map.get(label, 0)
        hotspots.append({
            "function_name": issue.get("function_name") or issue.get("message", "complex_function").split("'")[1] if "'" in (issue.get("message") or "") else "complex_function",
            "file": issue.get("file"),
            "line": issue.get("line_number"),
            "complexity": complexity,
            "risk_level": "High" if complexity >= 20 else "Medium" if complexity >= 10 else "Low",
            "source": issue.get("source"),
        })
    hotspots.sort(key=lambda entry: (-entry["complexity"], entry["file"] or "", entry["line"] or 0))
    return hotspots[:10]


def _per_file_summary(files: dict[str, str], findings: list) -> dict:
    grouped: dict[str, dict] = {}
    for path in files:
        grouped[path] = {"errors": 0, "warnings": 0, "complexity": "Low", "issues": 0}
    for finding in findings:
        file_path = finding.file
        if file_path not in grouped:
            grouped[file_path] = {"errors": 0, "warnings": 0, "complexity": "Low", "issues": 0}
        grouped[file_path]["issues"] += 1
        severity = finding.severity.value if hasattr(finding.severity, "value") else str(finding.severity)
        if severity in {"high", "critical"}:
            grouped[file_path]["errors"] += 1
        elif severity == "medium":
            grouped[file_path]["warnings"] += 1
        if finding.issue.startswith("COMPLEXITY"):
            grouped[file_path]["complexity"] = "High" if grouped[file_path]["complexity"] != "High" else "High"
    for data in grouped.values():
        if data["errors"] > 0 or data["warnings"] >= 3:
            data["complexity"] = "High" if data["warnings"] >= 3 else "Medium"
    return grouped


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}


@app.post("/analyze", response_model=FindingsResponse)
def analyze(request: AnalyzeRequest):
    """Runs the requested static-analysis tools (ruff, pylint, radon) over the submitted files."""
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
    tool_runs: list[dict] = []
    analyzers = {
        "ruff": run_ruff,
        "pylint": run_pylint,
        "radon": run_radon,
    }
    for tool in tools:
        started = perf_counter()
        try:
            tool_issues = analyzers[tool](files)
            raw_issues += tool_issues
            tool_runs.append({
                "tool": tool,
                "status": "completed",
                "finding_count": len(tool_issues),
                "duration_ms": round((perf_counter() - started) * 1000, 2),
                "findings": tool_issues,
            })
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
            tool_runs.append({
                "tool": tool,
                "status": "failed",
                "finding_count": 1,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
                "error": str(exc),
                "findings": [],
            })

    findings = normalize(raw_issues)
    quality_summary = _quality_summary(files, findings)
    quality_summary["quality_score"] = _quality_score(quality_summary)
    quality_summary["selected_tools"] = tools
    quality_summary["tool_runs"] = tool_runs
    quality_summary["tool_results"] = {item["tool"]: {"status": item["status"], "finding_count": item["finding_count"], "error": item.get("error"), "findings": item.get("findings", [])} for item in tool_runs}
    quality_summary["hotspots"] = _detect_hotspots(raw_issues)
    quality_summary["per_file"] = _per_file_summary(files, findings)

    return FindingsResponse(
        project_id=request.project_id,
        agent="code_quality",
        findings=findings,
        findings_count=len(findings),
        error="; ".join(tool_errors) if tool_errors else None,
        quality_summary=quality_summary,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
