"""
HTTP client for the Docker Sandbox Service (Shifa's sandbox-service).
The orchestrator never runs untrusted code itself — it always delegates
execution to this isolated service.
"""
import httpx

from app.config import settings


async def execute(project_id: str, files: dict[str, str]) -> dict:
    payload = {
        "project_id": project_id,
        "files": [{"path": p, "content": c} for p, c in files.items()],
    }

    async with httpx.AsyncClient(timeout=settings.sandbox_call_timeout_seconds) as client:
        try:
            resp = await client.post(f"{settings.sandbox_service_url}/execute", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            return {
                "project_id": project_id,
                "executed": False,
                "error": f"sandbox-service unreachable (not yet integrated?): {exc}",
            }
