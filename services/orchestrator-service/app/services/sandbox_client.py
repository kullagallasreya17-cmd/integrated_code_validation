"""
HTTP client for the Docker Sandbox Service (Shifa's sandbox-service).
The orchestrator never runs untrusted code itself — it always delegates
execution to this isolated service.
"""
import httpx

from app.config import settings


async def execute(project_id: str, files: dict[str, str]) -> dict:
    python_files = {path: content for path, content in files.items() if path.lower().endswith(".py")}
    if not python_files:
        return {"project_id": project_id, "executed": False, "error": "No Python files supplied"}

    selected_path = next(
        (path for path in python_files if path.rsplit("/", 1)[-1].lower() == "main.py"),
        next(iter(python_files)),
    )

    async with httpx.AsyncClient(timeout=settings.sandbox_call_timeout_seconds) as client:
        try:
            response = await client.post(
                f"{settings.sandbox_service_url}/execute",
                json={
                    "code": python_files[selected_path],
                    "filename": selected_path.rsplit("/", 1)[-1],
                },
            )
            response.raise_for_status()
            result = response.json()
            status = result.get("status")
            passed = status == "completed" and result.get("exit_code") == 0
            executed = status in {"completed", "failed", "timeout"}
            return {
                **result,
                "project_id": project_id,
                "selected_file": selected_path,
                "executed": executed,
                "passed": passed,
                "error": result.get("stderr") if status == "error" else None,
            }
        except httpx.HTTPError as exc:
            return {
                "project_id": project_id,
                "executed": False,
                "error": f"sandbox-service unreachable (not yet integrated?): {exc}",
            }
