"""
HTTP client for the Fix & Regeneration Service (Rakshitha's repair-service).
"""
import httpx

from app.config import settings


async def repair(project_id: str, files: dict[str, str], findings: list[dict], repair_attempt: int) -> dict:
    payload = {
        "project_id": project_id,
        "files": [{"path": p, "content": c} for p, c in files.items()],
        "findings": findings,
        "repair_attempt": repair_attempt,
    }

    async with httpx.AsyncClient(timeout=settings.repair_call_timeout_seconds) as client:
        try:
            resp = await client.post(f"{settings.repair_service_url}/repair", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            # Fall back to returning the code unchanged so the graph can
            # still reach validation (which will then correctly fail).
            return {
                "project_id": project_id,
                "repaired_files": [{"path": p, "content": c} for p, c in files.items()],
                "changelog": [],
                "error": f"repair-service unreachable (not yet integrated?): {exc}",
            }
