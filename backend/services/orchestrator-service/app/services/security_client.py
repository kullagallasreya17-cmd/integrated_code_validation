"""HTTP adapter for the team's per-file Security Agent API."""
import httpx

from app.config import settings
from app.services.finding_mapper import normalize_finding


async def analyze(project_id: str, files: dict[str, str], project_context: dict | None = None) -> dict:
    findings = []
    errors = []
    async with httpx.AsyncClient(timeout=settings.agent_call_timeout_seconds) as client:
        for path, content in files.items():
            try:
                response = await client.post(
                    f"{settings.security_service_url}/scan",
                    json={"code": content, "filename": path.rsplit("/", 1)[-1]},
                )
                response.raise_for_status()
                for item in response.json().get("findings", []):
                    findings.append(normalize_finding(item, path, "SEC", len(findings) + 1, "security"))
            except httpx.HTTPError as exc:
                errors.append(f"{path}: {exc}")

    return {
        "project_id": project_id,
        "agent": "security",
        "findings": findings,
        "findings_count": len(findings),
        "error": "; ".join(errors) if errors else None,
    }
