import difflib
from pathlib import Path

from app.services.ollama_service import generate_code


async def generate_fix(code: str, finding: str, severity: str) -> dict:

    prompt = f"""
You are a professional code repair assistant.

Your task is to analyze a code issue and propose a safe correction.

IMPORTANT RULES:
1. Do not invent unrelated changes.
2. Preserve the original functionality.
3. Fix only the reported issue unless another change is required.
4. Return valid Python code.
5. Do not modify any files.
6. Do not include markdown code fences around the fixed code.

CODE:
{code}

FINDING:
{finding}

SEVERITY:
{severity}

Return your answer using exactly this format:

PROBLEM:
<short description>

EXPLANATION:
<explain why the issue exists and why it matters>

RECOMMENDATION:
<explain the recommended fix>

FIXED_CODE:
<complete corrected source code>
"""

    response = await generate_code(prompt)

    problem = ""
    explanation = ""
    recommendation = ""
    fixed_code = ""

    sections = response.split("FIXED_CODE:")

    if len(sections) == 2:
        before_code = sections[0]
        fixed_code = sections[1].strip()

        parts = before_code.split("RECOMMENDATION:")

        if len(parts) == 2:
            recommendation = parts[1].strip()
            before_recommendation = parts[0]
        else:
            before_recommendation = before_code

        parts = before_recommendation.split("EXPLANATION:")

        if len(parts) == 2:
            explanation = parts[1].strip()
            problem_part = parts[0]
        else:
            problem_part = before_recommendation

        if "PROBLEM:" in problem_part:
            problem = problem_part.split("PROBLEM:", 1)[1].strip()

    return {
        "problem": problem,
        "explanation": explanation,
        "recommendation": recommendation,
        "fixed_code": fixed_code
    }


def create_diff(
    original_code: str,
    fixed_code: str,
    filename: str
) -> str:

    diff = difflib.unified_diff(
        original_code.splitlines(),
        fixed_code.splitlines(),
        fromfile=f"{filename} (original)",
        tofile=f"{filename} (fixed)",
        lineterm=""
    )

    return "\n".join(diff)


def apply_fix(
    original_code: str,
    fixed_code: str,
    filename: str
) -> tuple[str, str]:

    output_dir = Path("fixed_files")
    output_dir.mkdir(exist_ok=True)

    safe_filename = Path(filename).name

    output_path = output_dir / f"fixed_{safe_filename}"

    output_path.write_text(
        fixed_code,
        encoding="utf-8"
    )

    diff = create_diff(
        original_code,
        fixed_code,
        safe_filename
    )

    return str(output_path), diff