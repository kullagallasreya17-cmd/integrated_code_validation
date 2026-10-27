import ast
import json
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path


def _ruff_codes(code: str) -> Counter | None:
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
        return Counter(item.get("code", "") for item in json.loads(result.stdout or "[]"))


def validate_repair(original_code: str, candidate_code: str, language: str = "python") -> tuple[bool, str]:
    if language.lower() != "python":
        return False, f"Validation for {language} is not supported."
    try:
        ast.parse(candidate_code)
    except SyntaxError as exc:
        return False, f"Syntax error at line {exc.lineno}: {exc.msg}"

    try:
        original_findings = _ruff_codes(original_code)
        candidate_findings = _ruff_codes(candidate_code)
    except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return False, "Ruff could not complete code-quality validation."

    if original_findings is not None and candidate_findings is not None:
        introduced = [
            f"{code}: {count - original_findings[code]} new finding(s)"
            for code, count in candidate_findings.items()
            if count > original_findings[code]
        ]
        if introduced:
            return False, "Repair introduced Ruff findings: " + "; ".join(introduced[:5])
    return True, "Syntax and no-new-Ruff-findings checks passed."