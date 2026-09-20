"""
HTTP client for the Security Service.

NOTE: this is Rakshitha's service (security-service). It doesn't exist
yet, so this client fails gracefully — it returns an empty findings
list with an `error` note instead of raising, so the graph can keep
running end-to-end with placeholder data while the other services are
being built. Once security-service is up, no other code needs to
change: this client already speaks the shared Finding contract.
"""
import httpx

from app.config import settings


async def analyze(project_id: str, files: dict[str, str], project_context: dict | None = None) -> dict:
    payload = {
        "project_id": project_id,
        "files": [{"path": p, "content": c} for p, c in files.items()],
        "project_context": project_context or {},
    }

    async with httpx.AsyncClient(timeout=settings.agent_call_timeout_seconds) as client:
        try:
            resp = await client.post(f"{settings.security_service_url}/analyze", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {
                "project_id": project_id,
                "agent": "security",
                "findings": [],
                "findings_count": 0,
                "error": f"security-service unreachable (not yet integrated?): {exc}",
            }
