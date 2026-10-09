"""
HTTP client for the Fix & Regeneration Service (Rakshitha's repair-service).
"""
import httpx

from app.config import settings


async def repair(project_id: str, files: dict[str, str], findings: list[dict], repair_attempt: int) -> dict:
    repaired_files = dict(files)
    errors = []
    async with httpx.AsyncClient(timeout=settings.repair_call_timeout_seconds) as client:
        for finding in findings:
            path = finding.get("file")
            if path not in repaired_files:
                errors.append(f"repair finding references unknown file: {path}")
                continue
            try:
                response = await client.post(
                    f"{settings.repair_service_url}/analyze-fix",
                    json={
                        "code": repaired_files[path],
                        "finding": finding.get("description") or finding.get("issue", ""),
                        "severity": finding.get("severity", "medium"),
                    },
                )
                response.raise_for_status()
                fixed_code = response.json().get("fixed_code")
                if not isinstance(fixed_code, str) or not fixed_code.strip():
                    errors.append(f"repair service returned no fixed code for {path}")
                    continue
                repaired_files[path] = fixed_code
            except httpx.HTTPError as exc:
                errors.append(f"{path}: {exc}")

    return {
        "project_id": project_id,
        "mode": "targeted",
        "repaired_files": [{"path": path, "content": content} for path, content in repaired_files.items()],
        "error": "; ".join(errors) if errors else None,
    }
