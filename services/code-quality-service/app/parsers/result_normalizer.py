"""
Converts the raw, tool-specific issue dicts from ruff/pylint/radon into
the shared Finding contract so the Orchestrator can merge them with
Security and Bug/Resource findings without special-casing this service.
"""
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


def normalize(raw_issues: list[dict]) -> list[Finding]:
    """
    raw_issues: output of run_ruff / run_pylint / run_radon, concatenated.
    Returns a list of shared.schemas.finding.Finding, deduplicated by
    (file, line_number, code).
    """
    findings: list[Finding] = []
    seen: set[tuple] = set()

    for issue in raw_issues:
        dedup_key = (issue.get("file"), issue.get("line_number"), issue.get("code"))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        code = issue.get("code")
        source = issue.get("source")
        findings.append(
            Finding(
                finding_id=f"QUAL-{next(_counter):03d}",
                category=FindingCategory.CODE_QUALITY,
                severity=_severity(issue.get("severity_hint", "medium")),
                file=issue.get("file") or "unknown",
                line_number=issue.get("line_number"),
                issue=code or "unknown_issue",
                description=issue.get("message") or "",
                evidence=f"[{source}] {code}",
                recommendation=_recommendation_for(code),
                status=FindingStatus.OPEN,
                tool=source,
                subcategory=_subcategory(code, source).value,
            )
        )

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
