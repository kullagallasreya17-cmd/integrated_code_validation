import httpx
from fastapi import APIRouter, HTTPException

from app.config import settings

router = APIRouter(prefix="/results", tags=["results"])


@router.get("/{project_id}")
async def get_results(project_id: str):
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.get(
                f"{settings.orchestrator_url.rstrip('/')}/workflow/status/{project_id}"
            )
            response.raise_for_status()
            status = response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Orchestrator unavailable") from exc

    if status.get("status") != "completed":
        return {"project_id": project_id, "status": status.get("status", "unknown"), "report": None}
    return {
        "project_id": project_id,
        "status": status.get("status"),
        "report": status.get("result", {}).get("final_report", {}),
    }