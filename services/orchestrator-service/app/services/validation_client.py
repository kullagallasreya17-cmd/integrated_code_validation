"""HTTP adapter for the team's per-file Validation Agent API."""
import httpx

from app.config import settings
from app.services.finding_mapper import normalize_finding


async def validate(project_id: str, files: dict[str, str], original_findings: list[dict]) -> dict:
    findings = []
    errors = []
    all_valid = True
    python_files = {path: content for path, content in files.items() if path.lower().endswith(".py")}
    if not python_files:
        return {"project_id": project_id, "passed": False, "error": "No Python files supplied"}

    async with httpx.AsyncClient(timeout=settings.validation_call_timeout_seconds) as client:
        for path, content in python_files.items():
            try:
                response = await client.post(
                    f"{settings.validation_service_url}/validate",
                    json={"code": content, "filename": path.rsplit("/", 1)[-1]},
                )
                response.raise_for_status()
                result = response.json()
                for item in result.get("findings", []):
                    findings.append(normalize_finding(item, path, "VAL", len(findings) + 1, "code_quality"))
                if not result.get("valid", False):
                    all_valid = False
            except httpx.HTTPError as exc:
                errors.append(f"{path}: {exc}")

    return {
        "project_id": project_id,
        "passed": all_valid and not errors,
        "findings": findings,
        "findings_count": len(findings),
        "error": "; ".join(errors) if errors else None,
    }
