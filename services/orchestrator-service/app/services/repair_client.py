"""
HTTP client for the Fix & Regeneration Service (Rakshitha's repair-service).
"""
import httpx

from app.config import settings


async def repair(project_id: str, files: dict[str, str], findings: list[dict]) -> dict:
    request = {
        "project_id": project_id,
        "language": "python",
        "files": [{"path": path, "content": content} for path, content in files.items()],
        "findings": [
            {
                "file": finding.get("file", ""),
                "line": finding.get("line_number"),
                "type": finding.get("category") or finding.get("issue", "bug"),
                "severity": finding.get("severity", "medium"),
                "message": finding.get("description") or finding.get("issue", ""),
            }
            for finding in findings
        ],
    }
    async with httpx.AsyncClient(timeout=settings.repair_call_timeout_seconds) as client:
        response = await client.post(
            f"{settings.repair_service_url.rstrip('/')}/repair",
            json=request,
        )
        response.raise_for_status()
        result = response.json()

    repaired_files = dict(files)
    for repair_result in result.get("repairs", []):
        if repair_result.get("path") in repaired_files:
            repaired_files[repair_result["path"]] = repair_result.get("regenerated_code", repaired_files[repair_result["path"]])
    return {
        "project_id": project_id,
        "mode": "targeted",
        "status": result.get("status", "failed"),
        "repaired_files": [{"path": path, "content": content} for path, content in repaired_files.items()],
        "unresolved_findings": result.get("unresolved_findings", []),
        "validation_status": result.get("validation_status"),
        "error": None,
    }
