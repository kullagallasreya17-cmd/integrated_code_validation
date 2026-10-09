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

    return {
        "status": "completed",
        "filename": request.filename,
        "valid": len(findings) == 0,
        "total_findings": len(findings),
        "findings": findings,
        "metrics": metrics
    }