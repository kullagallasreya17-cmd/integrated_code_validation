from pydantic import BaseModel
from typing import List, Optional


class ValidationRequest(BaseModel):
    code: str
    filename: str = "main.py"


class ValidationFinding(BaseModel):
    type: str
    severity: str
    file: str
    line: Optional[int] = None
    column: Optional[int] = None
    message: str
    code: Optional[str] = None
    recommendation: str


class ValidationMetrics(BaseModel):
    lines_of_code: int
    functions: int
    classes: int
    imports: int
    max_function_length: int
    max_nesting_depth: int


class ValidationResponse(BaseModel):
    status: str
    filename: str
    valid: bool
    total_findings: int
    findings: List[ValidationFinding]
    metrics: ValidationMetrics