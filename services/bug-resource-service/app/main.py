import ast
from pathlib import PurePosixPath

from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator

from shared.schemas.finding import Finding, FindingCategory, FindingsResponse, Severity


MAX_FILES = 100
MAX_FILE_SIZE_BYTES = 500_000

app = FastAPI(
    title="Bug & Resource Analysis Service",
    description="Deterministic AST checks for common Python bug and resource risks.",
    version="1.0.0",
)


class ProjectFile(BaseModel):
    path: str
    content: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        path = PurePosixPath(normalized)
        has_windows_drive = bool(path.parts) and len(path.parts[0]) == 2 and path.parts[0][1] == ":"
        if not normalized or path.is_absolute() or has_windows_drive or ".." in path.parts:
            raise ValueError("file path must be relative and stay inside the project")
        if path.suffix.lower() != ".py":
            raise ValueError("only Python .py files are supported")
        return "/".join(path.parts)

    @field_validator("content")
    @classmethod
    def validate_content_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_FILE_SIZE_BYTES:
            raise ValueError("file exceeds the analysis size limit")
        return value


class AnalyzeRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    files: list[ProjectFile] = Field(min_length=1, max_length=MAX_FILES)
    project_context: dict = Field(default_factory=dict)

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("project_id must not be empty")
        return normalized

    @field_validator("files")
    @classmethod
    def validate_unique_paths(cls, value: list[ProjectFile]) -> list[ProjectFile]:
        paths = [file.path for file in value]
        if len(paths) != len(set(paths)):
            raise ValueError("project files must have unique paths")
        return value


def _is_open_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id == "open"
    return isinstance(node.func, ast.Attribute) and node.func.attr == "open"


def _is_mutable_default(node: ast.expr) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"list", "dict", "set"}


class BugResourceAnalyzer(ast.NodeVisitor):
    def __init__(self, filename: str, source: str, tree: ast.Module) -> None:
        self.filename = filename
        self.source_lines = source.splitlines()
        self.findings: list[Finding] = []
        self.counters = {"bug": 0, "resource": 0}
        self.managed_open_calls = self._find_managed_open_calls(tree)
        self.closed_names = self._find_closed_names(tree)
        self.open_assignments = self._find_open_assignments(tree)

    @staticmethod
    def _find_managed_open_calls(tree: ast.Module) -> set[int]:
        managed = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.With, ast.AsyncWith)):
                continue
            for item in node.items:
                managed.update(id(child) for child in ast.walk(item.context_expr) if _is_open_call(child))
        return managed

    @staticmethod
    def _find_closed_names(tree: ast.Module) -> set[str]:
        return {
            node.func.value.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "close"
            and isinstance(node.func.value, ast.Name)
        }

    @staticmethod
    def _find_open_assignments(tree: ast.Module) -> dict[int, str]:
        assignments: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and _is_open_call(node.value):
                assignments[id(node.value)] = node.targets[0].id
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and _is_open_call(node.value):
                assignments[id(node.value)] = node.target.id
        return assignments

    def _add_finding(
        self,
        category: FindingCategory,
        severity: Severity,
        code: str,
        node: ast.AST,
        description: str,
        recommendation: str,
        subcategory: str,
    ) -> None:
        kind = "bug" if category == FindingCategory.BUG else "resource"
        self.counters[kind] += 1
        line = getattr(node, "lineno", 1)
        evidence = self.source_lines[line - 1].strip()[:240] if 0 < line <= len(self.source_lines) else None
        self.findings.append(Finding(
            finding_id=f"{'BUG' if kind == 'bug' else 'RES'}-{self.counters[kind]:03d}",
            category=category,
            severity=severity,
            file=self.filename,
            line_number=line,
            issue=code,
            description=description,
            evidence=evidence,
            recommendation=recommendation,
            tool="bug_resource_ast",
            detected_by_tools=["ast"],
            subcategory=subcategory,
        ))

    def _check_function_defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        defaults = [*node.args.defaults, *(value for value in node.args.kw_defaults if value is not None)]
        if any(_is_mutable_default(default) for default in defaults):
            self._add_finding(
                FindingCategory.BUG,
                Severity.MEDIUM,
                "BUG001",
                node,
                "A mutable default argument is shared between function calls and may retain state unexpectedly.",
                "Use None as the default and create a new list, dictionary, or set inside the function.",
                "mutable_default",
            )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function_defaults(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function_defaults(node)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        catches_broad_error = node.type is None or (
            isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}
        )
        if catches_broad_error and node.body and all(isinstance(statement, ast.Pass) for statement in node.body):
            self._add_finding(
                FindingCategory.BUG,
                Severity.MEDIUM,
                "BUG002",
                node,
                "A broad exception is silently ignored, which can hide failures and leave work incomplete.",
                "Catch the expected exception types and handle or report the failure explicitly.",
                "exception_handling",
            )
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        if any(isinstance(statement, ast.Return) for statement in node.finalbody):
            self._add_finding(
                FindingCategory.BUG,
                Severity.HIGH,
                "BUG003",
                node,
                "A return in finally can suppress an exception or override an earlier return value.",
                "Move the return outside the finally block and reserve finally for cleanup.",
                "exception_handling",
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_open_call(node) and id(node) not in self.managed_open_calls:
            assigned_name = self.open_assignments.get(id(node))
            if assigned_name not in self.closed_names:
                self._add_finding(
                    FindingCategory.RESOURCE,
                    Severity.MEDIUM,
                    "RES001",
                    node,
                    "A file is opened outside a context manager and may remain open if an error occurs.",
                    "Use `with open(...) as file:` so the file is closed on every exit path.",
                    "file_lifecycle",
                )

        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            unbounded_read = method in {"readlines", "read_text"} or (method == "read" and not node.args and not node.keywords)
            if unbounded_read:
                self._add_finding(
                    FindingCategory.RESOURCE,
                    Severity.LOW,
                    "RES002",
                    node,
                    "This read loads all available content into memory at once, which can be costly for large inputs.",
                    "Process input incrementally or read a bounded number of bytes or lines.",
                    "memory_usage",
                )
        self.generic_visit(node)


def analyze_file(filename: str, source: str, start_ids: dict[str, int]) -> list[Finding]:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as error:
        line = error.lineno or 1
        finding = Finding(
            finding_id="BUG-000",
            category=FindingCategory.BUG,
            severity=Severity.HIGH,
            file=filename,
            line_number=line,
            issue="BUG000",
            description="Python syntax errors prevented AST-based bug and resource checks from inspecting this file.",
            evidence=(source.splitlines()[line - 1].strip()[:240] if line <= len(source.splitlines()) else None),
            recommendation="Fix the syntax error and rerun analysis.",
            tool="bug_resource_ast",
            detected_by_tools=["ast"],
            subcategory="syntax",
        )
        start_ids["bug"] += 1
        finding.finding_id = f"BUG-{start_ids['bug']:03d}"
        return [finding]

    analyzer = BugResourceAnalyzer(filename, source, tree)
    analyzer.visit(tree)
    findings = []
    for finding in analyzer.findings:
        kind = "bug" if finding.category == FindingCategory.BUG else "resource"
        start_ids[kind] += 1
        prefix = "BUG" if kind == "bug" else "RES"
        findings.append(finding.model_copy(update={"finding_id": f"{prefix}-{start_ids[kind]:03d}"}))
    return findings


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "bug-resource-service"}


@app.post("/analyze", response_model=FindingsResponse)
def analyze(request: AnalyzeRequest) -> FindingsResponse:
    findings: list[Finding] = []
    counters = {"bug": 0, "resource": 0}
    for project_file in request.files:
        findings.extend(analyze_file(project_file.path, project_file.content, counters))
    return FindingsResponse(
        project_id=request.project_id,
        agent="bug_resource",
        findings=findings,
        findings_count=len(findings),
    )