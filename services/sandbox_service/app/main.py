from fastapi import FastAPI
from pydantic import BaseModel, field_validator
import docker
import os
import uuid
import time

app = FastAPI(
    title="Sandbox Agent",
    description="Isolated code execution service",
    version="2.2.0"
)

docker_client = docker.from_env()

MAX_TIMEOUT = 30
MAX_OUTPUT = 50000
WORKSPACE_ROOT = os.getenv("SANDBOX_WORKSPACE_ROOT", "/sandbox-workspaces")
WORKSPACE_VOLUME = os.getenv("SANDBOX_WORKSPACE_VOLUME", "coding-validation-sandbox-workspaces")


class TestCase(BaseModel):
    input: str = ""
    expected: str | None = None


class CodeRequest(BaseModel):
    code: str
    filename: str = "main.py"
    timeout: int = 5
    stdin: str = ""
    test_cases: list[TestCase] = []

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value):
        if os.path.basename(value) != value or not value.endswith(".py"):
            raise ValueError("Only a Python filename is allowed")
        return value

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, value):
        if value < 1 or value > MAX_TIMEOUT:
            raise ValueError("Timeout must be between 1 and 30 seconds")
        return value


@app.get("/health")
def health():
    try:
        docker_client.ping()
    except Exception as error:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Docker execution engine is unavailable") from error
    return {"status": "healthy", "service": "sandbox-agent"}


def classify_error(status, stderr):

    if status == "timeout":
        return "Timeout"

    if status == "completed":
        return None

    if "SyntaxError" in stderr:
        return "SyntaxError"

    if "Traceback" in stderr:
        return "RuntimeError"

    return "ExecutionError"


def run_code(code, stdin, timeout, execution_id, filename):

    workspace = os.path.join(WORKSPACE_ROOT, execution_id)

    file_path = os.path.join(workspace, filename)
    input_path = os.path.join(workspace, "input.txt")
    container = None

    try:
        os.makedirs(workspace, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

        with open(input_path, "w", encoding="utf-8") as f:
            f.write(stdin)

        container = docker_client.containers.run(
            image="python:3.11-slim",
            command=[
                "sh",
                "-c",
                f"python /sandbox/{execution_id}/{filename} < /sandbox/{execution_id}/input.txt"
            ],
            volumes={
                WORKSPACE_VOLUME: {
                    "bind": "/sandbox",
                    "mode": "ro"
                }
            },
            working_dir="/sandbox",
            network_disabled=True,
            mem_limit="128m",
            nano_cpus=500000000,
            pids_limit=64,
            user="nobody",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            read_only=True,
            detach=True,
            remove=False,
            name=f"sandbox-exec-{execution_id}"
        )

        start = time.time()

        while True:
            container.reload()

            if container.status in ["exited", "dead"]:
                break

            if time.time() - start >= timeout:
                try:
                    container.kill()
                except Exception:
                    pass

                return {
                    "status": "timeout",
                    "error_type": "Timeout",
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "Execution timed out."
                }

            time.sleep(0.1)

        result = container.wait()

        stdout = container.logs(
            stdout=True,
            stderr=False
        ).decode("utf-8", errors="replace")[:MAX_OUTPUT]

        stderr = container.logs(
            stdout=False,
            stderr=True
        ).decode("utf-8", errors="replace")[:MAX_OUTPUT]

        status = (
            "completed"
            if result["StatusCode"] == 0
            else "failed"
        )

        return {
            "status": status,
            "error_type": classify_error(status, stderr),
            "exit_code": result["StatusCode"],
            "stdout": stdout,
            "stderr": stderr
        }

    except Exception as e:

        return {
            "status": "error",
            "error_type": "ExecutionError",
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e)
        }

    finally:

        if container:
            try:
                container.remove(force=True)
            except Exception:
                pass

        if os.path.exists(workspace):
            try:
                for root, dirs, files in os.walk(
                    workspace,
                    topdown=False
                ):
                    for file in files:
                        os.remove(os.path.join(root, file))

                    for directory in dirs:
                        os.rmdir(os.path.join(root, directory))

                os.rmdir(workspace)

            except Exception:
                pass


@app.post("/execute")
def execute_code(request: CodeRequest):

    execution_id = str(uuid.uuid4())

    if not request.test_cases:
        return run_code(
            request.code,
            request.stdin,
            request.timeout,
            execution_id,
            request.filename
        )

    results = []

    for i, test in enumerate(request.test_cases, 1):

        result = run_code(
            request.code,
            test.input,
            request.timeout,
            f"{execution_id}-{i}",
            request.filename
        )

        actual = result["stdout"].strip()
        expected = test.expected

        passed = (
            expected is None or
            actual == expected.strip()
        )

        results.append({
            "test_case": i,
            "input": test.input,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "status": result["status"],
            "error_type": result["error_type"],
            "stderr": result["stderr"]
        })

    return {
        "status": "completed",
        "total_tests": len(results),
        "passed": sum(x["passed"] for x in results),
        "failed": sum(not x["passed"] for x in results),
        "results": results
    }