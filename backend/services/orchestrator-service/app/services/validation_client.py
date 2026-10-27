"""HTTP adapter for the team's per-file Validation Agent API."""
import logging

import httpx

from app.config import settings
from app.services.finding_mapper import normalize_finding
from shared.languages import detect_language, source_files

logger = logging.getLogger(__name__)
VALIDATION_STATUSES = {"passed", "failed", "needs_review"}


async def validate(
    project_id: str,
    files: dict[str, str],
    original_findings: list[dict],
    sandbox_result: dict | None = None,
) -> dict:
    findings = []
    errors = []
    all_valid = True
    needs_review = False
    source_code_files = source_files(files)
    if not source_code_files:
        return {
            "project_id": project_id,
            "passed": False,
            "status": "error",
            "findings": [],
            "error": "No supported source files supplied to the validation service.",
        }
    language = detect_language(list(source_code_files))
    if language != "python":
        passed = bool(
            sandbox_result
            and sandbox_result.get("status") == "completed"
            and sandbox_result.get("passed", sandbox_result.get("exit_code") == 0)
        )
        return {
            "project_id": project_id,
            "passed": passed,
            "status": "passed" if passed else "failed",
            "findings": [],
            "findings_count": 0,
            "validator": (
                sandbox_result.get("validator")
                if sandbox_result and sandbox_result.get("validator")
                else "isolated_static_compilation"
            ),
            "message": (
                f"{language} source passed isolated static compilation."
                if passed else
                f"{language} validation did not pass isolated static compilation."
            ),
        }

    async with httpx.AsyncClient(timeout=settings.validation_call_timeout_seconds) as client:
        for path, content in source_code_files.items():
            try:
                response = await client.post(
                    f"{settings.validation_service_url}/validate",
                    json={"code": content, "filename": path.rsplit("/", 1)[-1]},
                )
                response.raise_for_status()
                result = response.json()
                if (
                    not isinstance(result, dict)
                    or not isinstance(result.get("valid"), bool)
                    or result.get("status") not in VALIDATION_STATUSES
                    or not isinstance(result.get("findings"), list)
                    or ("needs_review" in result and not isinstance(result["needs_review"], bool))
                ):
                    raise ValueError(f"Validation service returned an invalid response for {path}.")
                for item in result.get("findings", []):
                    if not isinstance(item, dict):
                        raise ValueError(f"Validation service returned a malformed finding for {path}.")
                    findings.append(normalize_finding(item, path, "VAL", len(findings) + 1, "code_quality"))
                if not result.get("valid", False):
                    all_valid = False
                needs_review = needs_review or result["status"] == "needs_review" or result.get("needs_review", False)
            except httpx.HTTPError as exc:
                logger.error(
                    "validation_request_failed file=%s exception=%s",
                    path,
                    type(exc).__name__,
                )
                errors.append(f"{path}: validation service request failed: {exc}")
            except (TypeError, ValueError) as exc:
                logger.error(
                    "validation_response_invalid file=%s exception=%s detail=%s",
                    path,
                    type(exc).__name__,
                    exc,
                )
                errors.append(f"{path}: {exc}")

    return {
        "project_id": project_id,
        "passed": all_valid and not errors,
        "status": "error" if errors else "failed" if not all_valid else "needs_review" if needs_review else "passed",
        "findings": findings,
        "findings_count": len(findings),
        "error": "; ".join(errors) if errors else None,
    }
