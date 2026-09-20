"""
HTTP client for the Validation Service (Shifa's validation-service).
Runs syntax checks, pytest, a security re-scan, and a quality re-scan,
and returns a pass/fail verdict the orchestrator routes on.
"""
import httpx

from app.config import settings


async def validate(project_id: str, files: dict[str, str], original_findings: list[dict]) -> dict:
    payload = {
        "project_id": project_id,
        "files": [{"path": p, "content": c} for p, c in files.items()],
        "original_findings": original_findings,
    }

    async with httpx.AsyncClient(timeout=settings.validation_call_timeout_seconds) as client:
        try:
            resp = await client.post(f"{settings.validation_service_url}/validate", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            # Treat an unreachable validation service as a failed
            # validation, not a silent pass — never let unverified code
            # through as "final".
            return {
                "project_id": project_id,
                "passed": False,
                "error": f"validation-service unreachable (not yet integrated?): {exc}",
            }
