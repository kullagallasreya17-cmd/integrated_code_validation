from fastapi import FastAPI

from .schemas import ValidationRequest, ValidationResponse
from .validator import validate_code


app = FastAPI(
    title="Code Validation Agent",
    description="Agent for validating Python code and detecting code quality issues",
    version="1.0.0"
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "validation-agent"
    }


@app.post("/validate", response_model=ValidationResponse)
def validate(request: ValidationRequest):
    findings, metrics = validate_code(
        request.code,
        request.filename
    )

    blocking_codes = {"SYNTAX", "VALIDATOR_ERROR", "VALIDATOR_TIMEOUT"}
    blocking_findings = [item for item in findings if item.get("code") in blocking_codes]
    if blocking_findings:
        status = "failed"
    elif findings:
        status = "needs_review"
    else:
        status = "passed"
    return {
        "status": status,
        "filename": request.filename,
        "valid": not blocking_findings,
        "needs_review": bool(findings) and not blocking_findings,
        "total_findings": len(findings),
        "findings": findings,
        "metrics": metrics
    }