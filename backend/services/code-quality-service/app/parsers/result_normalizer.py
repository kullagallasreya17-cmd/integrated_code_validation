"""
Converts the raw, tool-specific issue dicts from ruff/pylint/radon into
the shared Finding contract so the Orchestrator can merge them with
Security and Bug/Resource findings without special-casing this service.
"""
import re
from itertools import count

from shared.schemas.finding import Finding, FindingCategory, FindingStatus, Severity

_counter = count(1)


def _severity(raw: str) -> Severity:
    return {
        "low": Severity.LOW,
        "medium": Severity.MEDIUM,
        "high": Severity.HIGH,
        "critical": Severity.CRITICAL,
    }.get(raw, Severity.MEDIUM)


def _subcategory(code: str | None, source: str | None) -> FindingCategory:
    if code and code.startswith("COMPLEXITY"):
        return FindingCategory.COMPLEXITY
    if code and code.startswith("C01"):
        return FindingCategory.CONVENTION
    if code in {"F401", "F841"}:
        return FindingCategory.BUG
    if source == "pylint":
        return FindingCategory.MAINTAINABILITY
    return FindingCategory.STYLE


def _message_signature(message: str | None) -> str:
    if not message:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", message.lower()).strip()
    return " ".join(normalized.split())


def normalize(raw_issues: list[dict]) -> list[Finding]:
    """
    raw_issues: output of run_ruff / run_pylint / run_radon, concatenated.
    Returns a list of shared.schemas.finding.Finding, deduplicated by
    (file, line_number, normalized message) to reduce duplicate reports from
    multiple quality tools at the same location.
    """
    findings: list[Finding] = []
    finding_by_key: dict[tuple, Finding] = {}

    for issue in raw_issues:
        file_name = issue.get("file") or "unknown"
        line_number = issue.get("line_number")
        code = issue.get("code")
        source = issue.get("source")
        message_key = _message_signature(issue.get("message"))
        if code in {"F841", "W0612"} or "unused variable" in message_key:
            dedup_key = (file_name, line_number, "unused variable")
        else:
            dedup_key = (file_name, line_number, message_key)

        existing = finding_by_key.get(dedup_key)
        if existing is not None:
            detected_by_tools = list(existing.detected_by_tools or [])
            if source and source not in detected_by_tools:
                detected_by_tools.append(source)
            existing.detected_by_tools = detected_by_tools
            existing.evidence = f"{existing.evidence}; [{source}] {code}"
            continue

        finding = Finding(
                finding_id=f"QUAL-{next(_counter):03d}",
                category=FindingCategory.CODE_QUALITY,
                severity=_severity(issue.get("severity_hint", "medium")),
                file=file_name,
                line_number=line_number,
                issue=code or "unknown_issue",
                description=issue.get("message") or "",
                evidence=f"[{source}] {code}",
                recommendation=_recommendation_for(code),
                status=FindingStatus.OPEN,
                tool=source,
                detected_by_tools=[source] if source else None,
                subcategory=_subcategory(code, source).value,
            )
        finding_by_key[dedup_key] = finding
        findings.append(finding)

    return findings


def _recommendation_for(code: str | None) -> str:
    if not code:
        return "Review and address the reported issue."
    if code.startswith("COMPLEXITY"):
        return "Break this function into smaller functions to reduce branching."
    if code in ("F401",):
        return "Remove the unused import."
    if code in ("F841",):
        return "Remove the unused variable or use it."
    if code.startswith("C01"):
        return "Add a docstring."
    return "Review and address the reported issue."
