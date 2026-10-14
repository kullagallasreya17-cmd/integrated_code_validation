import asyncio

import httpx
from fastapi import APIRouter, Depends

from app.config import settings
from app.security import get_current_user

router = APIRouter(prefix="/api/system", tags=["system"], dependencies=[Depends(get_current_user)])

SERVICES = {
    "orchestrator": settings.orchestrator_url,
    "code_quality": settings.quality_service_url,
    "security": settings.security_service_url,
    "repair": settings.repair_service_url,
    "sandbox": settings.sandbox_service_url,
    "validation": settings.validation_service_url,
}


async def _check_service(client: httpx.AsyncClient, name: str, url: str | None) -> tuple[str, dict]:
    if not url:
        return name, {"status": "not_configured", "healthy": False}
    try:
        response = await client.get(f"{url.rstrip('/')}/health")
        response.raise_for_status()
        payload = response.json() if "application/json" in response.headers.get("content-type", "") else {}
        return name, {"status": "healthy", "healthy": True, "details": payload}
    except (httpx.HTTPError, ValueError):
        return name, {"status": "unavailable", "healthy": False}


@router.get("/agents")
async def agent_health() -> dict:
    async with httpx.AsyncClient(timeout=3.0) as client:
        checks = await asyncio.gather(*(
            _check_service(client, name, url) for name, url in SERVICES.items()
        ))
        bug_resource = await _check_service(client, "bug_resource", settings.bug_resource_service_url)
    services = dict(checks)
    services[bug_resource[0]] = bug_resource[1]
    return {
        "services": services,
        "ready": sum(1 for item in services.values() if item["healthy"]),
        "configured": len(services),
    }