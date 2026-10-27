import ast
import json
import os
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path


def _ruff_diagnostics(code: str) -> list[dict] | None:
    ruff_path = shutil.which("ruff")
    if not ruff_path:
        return None

    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "candidate.py"
        file_path.write_text(code, encoding="utf-8")
        result = subprocess.run(
            [ruff_path, "check", "--select", "E,W,F", "--output-format", "json", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode not in (0, 1):
            raise OSError("Ruff could not complete code-quality validation")
        return json.loads(result.stdout or "[]")


def _run_language_check(command: list[str], timeout: int = 15, env: dict[str, str] | None = None) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except FileNotFoundError:
        return False, f"Required validation tool is not installed: {command[0]}"
    except subprocess.TimeoutExpired:
        return False, f"{command[0]} validation timed out."
    except OSError as exc:
        return False, f"Could not run {command[0]} validation: {exc}"

    if result.returncode == 0:
        return True, f"{command[0]} validation passed."
    details = (result.stderr or result.stdout).strip()
    return False, details[:1200] or f"{command[0]} validation failed."


def _validate_non_python(candidate_code: str, language: str, filename: str) -> tuple[bool, str]:
    source_name = Path(filename).name
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source_path = root / source_name
        source_path.write_text(candidate_code, encoding="utf-8")

        if language == "javascript":
            command = ["node", "--check", str(source_path)]
        elif language == "typescript":
            command = [
                "tsc", "--noEmit", "--target", "ES2020", "--module", "commonjs",
                "--skipLibCheck", str(source_path),
            ]
        elif language == "java":
            classes_path = root / "classes"
            classes_path.mkdir()
            command = ["javac", "-Xlint:all", "-d", str(classes_path), str(source_path)]
        elif language == "c":
            command = ["gcc", "-std=c11", "-Wall", "-Wextra", "-fsyntax-only", str(source_path)]
        elif language == "cpp":
            command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-fsyntax-only", str(source_path)]
        elif language == "go":
            go_env = os.environ.copy()
            go_env.update({
                "GO111MODULE": "off",
                "GOCACHE": str(root / "go-cache"),
                "GOPATH": str(root / "go-path"),
            })
            return _run_language_check(
                ["go", "test", str(source_path)],
                timeout=60,
                env=go_env,
            )
        elif language == "csharp":
            command = [
                "mcs", "-warn:4", "-target:library",
                f"-out:{root / 'candidate.dll'}", str(source_path),
            ]
        else:
            return False, f"Repair validation does not support language '{language}'."
        return _run_language_check(command)


def validate_repair(
    original_code: str,
    candidate_code: str,
    language: str = "python",
    filename: str = "main.py",
) -> tuple[bool, str]:
    normalized_language = language.strip().lower()
    if not candidate_code.strip():
        return False, "Repair candidate is empty."
    if normalized_language != "python":
        return _validate_non_python(candidate_code, normalized_language, filename)

    try:
        ast.parse(candidate_code)
    except SyntaxError as exc:
        return False, f"Syntax error at line {exc.lineno}: {exc.msg}"

    try:
        original_findings = _ruff_diagnostics(original_code)
        candidate_findings = _ruff_diagnostics(candidate_code)
    except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return False, "Ruff could not complete code-quality validation."

    if original_findings is not None and candidate_findings is not None:
        def identity(item: dict) -> tuple:
            return item.get("code", ""), item.get("message", "")

        remaining_original = Counter(identity(item) for item in original_findings)
        introduced = []
        for item in candidate_findings:
            key = identity(item)
            if remaining_original[key]:
                remaining_original[key] -= 1
                continue
            location = item.get("location", {})
            introduced.append(
                f"{item.get('code', 'unknown')} at line {location.get('row', '?')}, "
                f"column {location.get('column', '?')}"
            )
        if introduced:
            return False, "Repair introduced Ruff findings: " + "; ".join(introduced[:5])
    return True, "Syntax and no-new-Ruff-findings checks passed."