from fastapi import FastAPI
from pathlib import PurePosixPath
import json
import re
import tomllib
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from pydantic import BaseModel, Field, field_validator, model_validator
from shared.languages import adapter_for_language, detect_language, is_source_path, validate_project_path
import docker
import os
import shutil
import uuid
import time

app = FastAPI(
    title="Sandbox Agent",
    description="Isolated code execution service",
    version="2.2.0"
)

docker_client = docker.from_env()

MAX_TIMEOUT = 60
DJANGO_CHECK_TIMEOUT = MAX_TIMEOUT
MAX_OUTPUT = 50000
MAX_FILES = 100
MAX_PROJECT_CHARACTERS = 1_000_000
WORKSPACE_ROOT = os.getenv("SANDBOX_WORKSPACE_ROOT", "/sandbox-workspaces")
WORKSPACE_VOLUME = os.getenv("SANDBOX_WORKSPACE_VOLUME", "coding-validation-sandbox-workspaces")
DJANGO_RUNTIME_IMAGE = os.getenv("SANDBOX_DJANGO_RUNTIME_IMAGE", "coding-validation-agent-frontend-sandbox-runtime:latest")
STANDALONE_RUNTIME_IMAGE = os.getenv("SANDBOX_DJANGO_RUNTIME_IMAGE", "coding-validation-agent-frontend-sandbox:latest")
MANIFEST_NAMES = {"requirements.txt", "pyproject.toml", "package.json", "package-lock.json", "tsconfig.json", "pom.xml", "build.gradle", "build.gradle.kts", "go.mod", "go.sum"}
SUPPORTED_RUNTIME_PACKAGES = {
    "django": "5.2.4",
    "asgiref": "3.9.1",
    "sqlparse": "0.5.3",
}
DJANGO_MODULES = {"admin.py", "apps.py", "asgi.py", "models.py", "settings.py", "urls.py", "views.py", "wsgi.py"}
DJANGO_SETTINGS_PATTERN = re.compile(r"DJANGO_SETTINGS_MODULE[\"']?\s*[,=]\s*[\"']([^\"']+)[\"']")
NODE_GLOBALS = ("console", "process", "Buffer", "__dirname", "module", "require")
BROWSER_GLOBALS = (
    "window",
    "document",
    "XMLHttpRequest",
    "fetch",
    "navigator",
    "location",
    "localStorage",
    "sessionStorage",
    "HTMLElement",
    "Node",
    "alert",
)


class TestCase(BaseModel):
    input: str = ""
    expected: str | None = None


class CodeRequest(BaseModel):
    code: str = ""
    filename: str = "main.py"
    files: dict[str, str] = Field(default_factory=dict)
    timeout: int = 20
    stdin: str = Field(default="", max_length=100_000)
    test_cases: list[TestCase] = Field(default_factory=list)
    validation_only: bool = False
    analysis_only: bool = False

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        normalized = validate_project_path(value)
        if not is_source_path(normalized):
            raise ValueError("The sandbox entry filename must be a supported source file")
        return normalized

    @field_validator("files")
    @classmethod
    def validate_files(cls, files: dict[str, str]) -> dict[str, str]:
        if len(files) > MAX_FILES:
            raise ValueError(f"A project may contain at most {MAX_FILES} files")
        normalized_files = {}
        total_characters = 0
        for name, content in files.items():
            relative_path = validate_project_path(name)
            if relative_path in normalized_files:
                raise ValueError("Project file paths must be unique")
            normalized_files[relative_path] = content
            total_characters += len(content)
        if total_characters > MAX_PROJECT_CHARACTERS:
            raise ValueError("Project exceeds the sandbox input limit")
        return normalized_files

    @model_validator(mode="after")
    def select_entry_file(self):
        if not self.files:
            self.files = {self.filename: self.code}
        if self.filename not in self.files:
            raise ValueError("The entry file must be included in the project files")
        if detect_language(list(self.files)) is None:
            raise ValueError("At least one supported source file is required")
        self.code = self.files[self.filename]
        return self

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, value):
        if value < 1 or value > MAX_TIMEOUT:
            raise ValueError(f"Timeout must be between 1 and {MAX_TIMEOUT} seconds")
        return value


@app.get("/health", responses={503: {"description": "Docker execution engine is unavailable"}})
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


def _write_workspace(files: dict[str, str], stdin: str, workspace: str) -> None:
    os.makedirs(workspace, exist_ok=True)
    for relative_path, content in files.items():
        file_path = os.path.join(workspace, *PurePosixPath(relative_path).parts)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(content)
    input_path = os.path.join(workspace, "input.txt")
    with open(input_path, "w", encoding="utf-8") as file:
        file.write(stdin)

def _start_execution_container(
    execution_id: str,
    filename: str,
    image: str = STANDALONE_RUNTIME_IMAGE,
    command: list[str] | None = None,
    working_directory: str | None = None,
):
    workspace = f"/sandbox/{execution_id}"
    return docker_client.containers.run(
        image=image,
        command=command or [
            "sh",
            "-c",
            'exec python "$1" < "$2"',
            "sandbox-run",
            f"{workspace}/{filename}",
            f"{workspace}/input.txt",
        ],
        volumes={WORKSPACE_VOLUME: {"bind": "/sandbox", "mode": "ro"}},
        working_dir=working_directory or workspace,
        tmpfs={"/tmp": "rw,exec,nosuid,mode=1777,size=256m"},
        environment={
            "PYTHONPATH": workspace,
            "GOCACHE": "/tmp/go-cache",
            "GOPATH": "/tmp/go-path",
            "JAVA_TOOL_OPTIONS": "-Xmx192m -XX:ActiveProcessorCount=1",
            "HOME": "/tmp/home",
            "DOTNET_CLI_HOME": "/tmp/dotnet-home",
            "NUGET_PACKAGES": "/tmp/nuget-packages",
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
            "DOTNET_NOLOGO": "1",
        },
        network_disabled=True,
        mem_limit="512m",
        nano_cpus=1000000000,
        pids_limit=64,
        user="nobody",
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        read_only=True,
        detach=True,
        remove=False,
        name=f"sandbox-exec-{execution_id}",
    )

def _wait_for_container(container, timeout: int) -> bool:
    start = time.time()
    while True:
        container.reload()
        if container.status in {"exited", "dead"}:
            return True
        if time.time() - start >= timeout:
            try:
                container.kill()
            except Exception:
                pass
            return False
        time.sleep(0.1)


def _container_result(container) -> dict:
    result = container.wait()
    stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")[:MAX_OUTPUT]
    stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")[:MAX_OUTPUT]
    status = "completed" if result["StatusCode"] == 0 else "failed"
    return {
        "status": status,
        "executed": True,
        "passed": status == "completed",
        "error_type": classify_error(status, stderr),
        "exit_code": result["StatusCode"],
        "stdout": stdout,
        "stderr": stderr,
    }


def _cleanup_execution(container, workspace: str) -> None:
    if container:
        try:
            container.remove(force=True)
        except Exception:
            pass
    shutil.rmtree(workspace, ignore_errors=True)


def run_code(files, stdin, timeout, execution_id, filename, *, image=STANDALONE_RUNTIME_IMAGE, command=None, working_directory=None):
    workspace = os.path.join(WORKSPACE_ROOT, execution_id)
    container = None
    try:
        _write_workspace(files, stdin, workspace)
        container = _start_execution_container(execution_id, filename, image, command, working_directory)
        if not _wait_for_container(container, timeout):
            return {
                "status": "timeout",
            "executed": True,
            "passed": False,
                "error_type": "Timeout",
                "exit_code": -1,
                "stdout": "",
                "stderr": "Execution timed out.",
            }
        return _container_result(container)

    except Exception as e:
        return {
            "status": "unavailable",
            "executed": False,
            "passed": False,
            "error_type": "SandboxUnavailable",
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "error": "The isolated execution container could not be started.",
        }
    finally:
        _cleanup_execution(container, workspace)


def _manifest_requirements(files: dict[str, str]) -> tuple[list[str], str | None]:
    requirements = []
    try:
        for path, content in files.items():
            name = PurePosixPath(path).name.lower()
            if name == "requirements.txt":
                parsed, error = _parse_requirements_file(content)
                if error:
                    return [], error
                requirements.extend(parsed)
            elif name == "pyproject.toml":
                parsed, error = _parse_pyproject(content)
                if error:
                    return [], error
                requirements.extend(parsed)
    except (tomllib.TOMLDecodeError, KeyError, TypeError):
        return [], "The dependency manifest could not be parsed."
    return requirements, None


def _parse_requirements_file(content: str) -> tuple[list[str], str | None]:
    requirements = []
    for raw_line in content.splitlines():
        line = raw_line.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-", ".", "git+", "http:", "https:")):
            return [], "Dependency options and direct URLs are not allowed in the isolated runtime."
        requirements.append(line)
    return requirements, None


def _parse_pyproject(content: str) -> tuple[list[str], str | None]:
    project = tomllib.loads(content).get("project")
    if project is None:
        return [], "pyproject.toml must declare dependencies using the PEP 621 [project] table."
    dependencies = project.get("dependencies", [])
    if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
        return [], "pyproject.toml dependencies must be a list of PEP 508 requirements."
    return dependencies, None


def _requirement_error(raw_requirement: str) -> tuple[str, str] | None:
    try:
        requirement = Requirement(raw_requirement)
    except InvalidRequirement:
        return "unsupported_project", "A dependency declaration is not a supported PEP 508 requirement."
    if requirement.url or requirement.extras:
        return "unsupported_project", "Direct references and optional dependency extras are not supported in the offline runtime."
    if requirement.marker and not requirement.marker.evaluate():
        return None
    package = canonicalize_name(requirement.name)
    installed = SUPPORTED_RUNTIME_PACKAGES.get(package)
    if installed is None or not requirement.specifier.contains(Version(installed), prereleases=True):
        return "dependency_missing", f"Dependency '{requirement.name}' is not available in the prebuilt offline runtime."
    return None


def _dependency_error(files: dict[str, str]) -> tuple[str, str] | None:
    requirements, error = _manifest_requirements(files)
    if error:
        return "unsupported_project", error
    for requirement in requirements:
        error = _requirement_error(requirement)
        if error:
            return error
    return None


def _django_project(files: dict[str, str]) -> dict | None:
    python_paths = [path for path in files if path.lower().endswith(".py")]
    framework_files = [path for path in python_paths if PurePosixPath(path).name.lower() in DJANGO_MODULES]
    manage_paths = [path for path in python_paths if PurePosixPath(path).name.lower() == "manage.py"]
    if not framework_files and not manage_paths:
        return None

    for manage_path in manage_paths:
        manage_root = PurePosixPath(manage_path).parent
        match = DJANGO_SETTINGS_PATTERN.search(files[manage_path])
        settings_path = match.group(1).replace(".", "/") + ".py" if match else None
        root_prefix = "" if str(manage_root) == "." else f"{manage_root}/"
        settings_available = any(
            path == f"{root_prefix}{settings_path}" or path.startswith(root_prefix) and PurePosixPath(path).name == "settings.py"
            for path in python_paths
        )
        if settings_available:
            return {"manage_path": manage_path, "project_root": str(manage_root)}
    return {
        "status": "project_incomplete",
        "error": "Django project files were detected, but a complete manage.py and settings.py project was not supplied.",
    }


def _entry_file(files: dict[str, str], language: str, requested: str) -> str:
    source_paths = [path for path in files if is_source_path(path)]
    candidates = {
        "javascript": ("index.js", "main.js", "app.js"),
        "typescript": ("index.ts", "main.ts", "app.ts"),
        "java": ("Main.java",),
        "c": ("main.c",),
        "cpp": ("main.cpp", "main.cc", "main.cxx"),
        "go": ("main.go",),
        "csharp": ("Program.cs", "Main.cs"),
    }.get(language, ())
    by_basename = {PurePosixPath(path).name.lower(): path for path in source_paths}
    for candidate in candidates:
        if candidate.lower() in by_basename:
            return by_basename[candidate.lower()]
    if requested in source_paths and PurePosixPath(requested).suffix.lower() not in {".h", ".hh", ".hpp", ".hxx"}:
        return requested
    return next(
        (path for path in source_paths if PurePosixPath(path).suffix.lower() not in {".h", ".hh", ".hpp", ".hxx"}),
        requested,
    )


def _javascript_analysis_globals(files: dict[str, str], source_paths: list[str]) -> tuple[str, ...]:
    source = "\n".join(files[path] for path in source_paths)
    browser_project = any(
        PurePosixPath(path).suffix.lower() == ".html"
        for path in files
    )
    for path, content in files.items():
        if PurePosixPath(path).name.lower() != "package.json":
            continue
        try:
            manifest = json.loads(content)
        except json.JSONDecodeError:
            continue
        if not isinstance(manifest, dict):
            continue
        dependencies = {
            **(manifest.get("dependencies") if isinstance(manifest.get("dependencies"), dict) else {}),
            **(manifest.get("devDependencies") if isinstance(manifest.get("devDependencies"), dict) else {}),
        }
        browser_project |= bool(
            manifest.get("browser")
            or {"react", "react-dom", "vue", "@angular/core", "svelte", "next", "nuxt"} & dependencies.keys()
        )
    uses_browser_apis = re.search(
        r"\b(?:window|document|XMLHttpRequest|navigator|location|localStorage|sessionStorage|HTMLElement)\b",
        source,
    )
    if browser_project or uses_browser_apis:
        return (*NODE_GLOBALS, *BROWSER_GLOBALS)
    return NODE_GLOBALS


def _language_execution_plan(request: CodeRequest, language: str) -> dict:
    adapter = adapter_for_language(language)
    if adapter is None or adapter["support"] == "unsupported":
        return {
            "status": "unsupported_project",
            "error": f"No validation adapter is registered for language {language!r}.",
        }
    filename = _entry_file(request.files, language, request.filename)
    entry = f"/sandbox/{{execution_id}}/{filename}"
    input_path = "/sandbox/{execution_id}/input.txt"
    source_paths = [
        f"/sandbox/{{execution_id}}/{path}"
        for path in request.files
        if is_source_path(path)
    ]
    if request.analysis_only:
        javascript_globals = " ".join(
            f"--global {name}"
            for name in _javascript_analysis_globals(request.files, [
                path for path in request.files if is_source_path(path)
            ])
        )
        analyzers = {
            "javascript": (
                f'for file do report=$(eslint --no-config-lookup --no-warn-ignored --stdin --stdin-filename "$file" {javascript_globals} --rule "no-undef:error" --rule "no-unused-vars:error" --format json < "$file"); code=$?; [ "$code" -le 1 ] || {{ printf "%s\\n" "$report" >&2; exit "$code"; }}; printf "%s" "$report" | node -e \'let input="";process.stdin.on("data",chunk=>input+=chunk);process.stdin.on("end",()=>{{for(const file of JSON.parse(input)){{for(const message of file.messages){{console.log(file.filePath+":"+ (message.line||1)+":"+(message.column||1)+": "+message.message)}}}}}})\' || exit $?; done',
                source_paths,
                "ESLint",
            ),
            "typescript": (
                'tsc --noEmit --target ES2020 --module commonjs --skipLibCheck "$@"',
                [path for path in source_paths if PurePosixPath(path).suffix.lower() in {".ts", ".tsx"}],
                "TypeScript compiler",
            ),
            "java": (
                'checkstyle -c /opt/coding-validation-checkstyle.xml "$@"; style=$?; mkdir -p /tmp/java-out && javac -Xlint:all -d /tmp/java-out "$@"; compile=$?; [ "$style" -eq 0 ] && [ "$compile" -eq 0 ]',
                [path for path in source_paths if path.lower().endswith(".java")],
                "JDK compiler",
            ),
            "c": (
                'cppcheck --error-exitcode=0 --enable=warning,style,performance,portability --template=gcc --quiet "$@" 2>&1',
                [path for path in source_paths if path.lower().endswith(".c")],
                "Cppcheck",
            ),
            "cpp": (
                'cppcheck --error-exitcode=0 --enable=warning,style,performance,portability --template=gcc --quiet "$@" 2>&1',
                [path for path in source_paths if PurePosixPath(path).suffix.lower() in {".cc", ".cpp", ".cxx"}],
                "Cppcheck",
            ),
            "go": (
                'mkdir -p /tmp/go-src; index=0; for file do index=$((index + 1)); cp "$file" "/tmp/go-src/source-${index}.go"; done; export GO111MODULE=off; go vet /tmp/go-src/*.go',
                [path for path in source_paths if path.lower().endswith(".go")],
                "Go vet",
            ),
            "csharp": (
                'mcs -r:System.Data -warn:4 -target:library -out:/tmp/validation.dll "$@"',
                [path for path in source_paths if path.lower().endswith(".cs")],
                "Mono C# compiler",
            ),
        }
        if language == "csharp":
            project_paths = [
                f"/sandbox/{{execution_id}}/{path}"
                for path in request.files
                if path.lower().endswith((".csproj", ".sln"))
            ]
            if project_paths:
                analyzers["csharp"] = (
                    'mkdir -p /tmp/home /tmp/dotnet-home /tmp/nuget-packages /tmp/dotnet-out /tmp/dotnet-obj && dotnet build "$1" --nologo --verbosity quiet --output /tmp/dotnet-out -p:BaseIntermediateOutputPath=/tmp/dotnet-obj/',
                    [project_paths[0]],
                    ".NET SDK",
                )
        command, arguments, toolchain = analyzers[language]
        if not arguments:
            return {
                "status": "unsupported_project",
                "error": f"No source files were supplied for {language} analysis.",
            }
        return {
            "status": None,
            "filename": filename,
            "image": STANDALONE_RUNTIME_IMAGE,
            "command": ["sh", "-c", command, "sandbox-analyze", *arguments],
            "working_directory": "/sandbox",
            "check_type": "static_analysis",
            "minimum_timeout": 45 if language in {"go", "csharp"} else 0,
            "validator": toolchain,
        }
    if request.validation_only:
        compiler_plans = {
            "javascript": (
                'for file do node --check "$file" || exit $?; done',
                source_paths,
                "Node.js syntax checker",
            ),
            "typescript": (
                'tsc --noEmit --target ES2020 --module commonjs --skipLibCheck "$@"',
                [path for path in source_paths if PurePosixPath(path).suffix.lower() in {".ts", ".tsx"}],
                "TypeScript compiler",
            ),
            "java": (
                'mkdir -p /tmp/java-out && javac -Xlint:all -d /tmp/java-out "$@"',
                [path for path in source_paths if path.lower().endswith(".java")],
                "JDK compiler",
            ),
            "c": (
                'gcc -std=c11 -Wall -Wextra -fsyntax-only "$@"',
                [path for path in source_paths if path.lower().endswith(".c")],
                "GCC",
            ),
            "cpp": (
                'g++ -std=c++17 -Wall -Wextra -fsyntax-only "$@"',
                [path for path in source_paths if PurePosixPath(path).suffix.lower() in {".cc", ".cpp", ".cxx"}],
                "G++",
            ),
            "go": (
                'mkdir -p /tmp/go-src; index=0; for file do index=$((index + 1)); cp "$file" "/tmp/go-src/source-${index}.go"; done; export GO111MODULE=off; go build -o /tmp/go-validation /tmp/go-src/*.go',
                [path for path in source_paths if path.lower().endswith(".go")],
                "Go compiler",
            ),
            "csharp": (
                'mcs -r:System.Data -target:library -out:/tmp/validation.dll "$@"',
                [path for path in source_paths if path.lower().endswith(".cs")],
                "Mono C# compiler",
            ),
        }
        if language == "csharp":
            project_paths = [
                f"/sandbox/{{execution_id}}/{path}"
                for path in request.files
                if path.lower().endswith((".csproj", ".sln"))
            ]
            if project_paths:
                compiler_plans["csharp"] = (
                    'mkdir -p /tmp/home /tmp/dotnet-home /tmp/nuget-packages /tmp/dotnet-out /tmp/dotnet-obj && dotnet build "$1" --nologo --verbosity quiet --output /tmp/dotnet-out -p:BaseIntermediateOutputPath=/tmp/dotnet-obj/',
                    [project_paths[0]],
                    ".NET SDK",
                )
        command, arguments, toolchain = compiler_plans[language]
        if not arguments:
            return {
                "status": "unsupported_project",
                "error": f"No compilable source files were supplied for {language}.",
            }
        return {
            "status": None,
            "filename": filename,
            "image": STANDALONE_RUNTIME_IMAGE,
            "command": ["sh", "-c", command, "sandbox-run", *arguments],
            "working_directory": "/sandbox",
            "check_type": "static_compilation",
            "minimum_timeout": 45 if language == "go" else 0,
            "validator": toolchain,
        }
    commands = {
        "javascript": (
            'exec node "$1" < "$2"',
            [entry, input_path],
        ),
        "typescript": (
            'mkdir -p /tmp/ts-out && tsc --target ES2020 --module commonjs --skipLibCheck --rootDir "$(dirname "$1")" --outDir /tmp/ts-out "$1" && base=$(basename "$1") && exec node "/tmp/ts-out/${base%.*}.js" < "$2"',
            [entry, input_path],
        ),
        "java": (
            'mkdir -p /tmp/java-out && javac -d /tmp/java-out "$1" && exec java -cp /tmp/java-out "$2" < "$3"',
            [
                entry,
                re.search(r"(?m)^\s*package\s+([A-Za-z_][\w.]*)\s*;", request.files[filename]).group(1) + "." + PurePosixPath(filename).stem
                if re.search(r"(?m)^\s*package\s+([A-Za-z_][\w.]*)\s*;", request.files[filename])
                else PurePosixPath(filename).stem,
                input_path,
            ],
        ),
        "c": (
            'gcc -std=c11 "$1" -o /tmp/program && exec /tmp/program < "$2"',
            [entry, input_path],
        ),
        "cpp": (
            'g++ -std=c++17 "$1" -o /tmp/program && exec /tmp/program < "$2"',
            [entry, input_path],
        ),
        "go": (
            'mkdir -p /tmp/go-src; index=0; while [ "$#" -gt 1 ]; do index=$((index + 1)); cp "$1" "/tmp/go-src/source-${index}.go"; shift; done; export GO111MODULE=off; go run /tmp/go-src/*.go < "$1"',
            [*source_paths, input_path],
        ),
        "csharp": (
            'mcs -r:System.Data -out:/tmp/program.exe "$1" && exec mono /tmp/program.exe < "$2"',
            [entry, input_path],
        ),
    }
    if language not in commands:
        return {"status": "unsupported_project", "error": f"No isolated runtime is configured for {language}."}
    command, arguments = commands[language]
    return {
        "status": None,
        "filename": filename,
        "image": STANDALONE_RUNTIME_IMAGE,
        "command": ["sh", "-c", command, "sandbox-run", *arguments],
        "working_directory": "/sandbox",
        "check_type": "compile_and_execute",
        "minimum_timeout": 45 if language == "go" else 0,
        "validator": "isolated compile and execution",
    }


def _execution_plan(request: CodeRequest) -> dict:
    language = detect_language(list(request.files))
    if language is None:
        return {"status": "unsupported_project", "error": "No supported source files were supplied."}
    if language != "python":
        return _language_execution_plan(request, language)
    django = _django_project(request.files)
    if django and django.get("status"):
        return django
    dependency_error = _dependency_error(request.files)
    if dependency_error:
        return {"status": dependency_error[0], "error": dependency_error[1]}
    if django:
        manage_path = django["manage_path"]
        project_root = django["project_root"]
        if request.test_cases:
            return {"status": "unsupported_project", "error": "Django projects run the configured manage.py check; standalone test_cases are not applied."}
        return {
            "status": None,
            "filename": manage_path,
            "image": DJANGO_RUNTIME_IMAGE,
            "command": [
                "sh",
                "-c",
                'cd "$1" && exec python "$2" "$3"',
                "sandbox-run",
                f"/sandbox/{{execution_id}}/{project_root}",
                f"/sandbox/{{execution_id}}/{manage_path}",
                "check",
            ],
            "working_directory": "/sandbox",
            "check_type": "django_check",
        }

    selected_path = request.filename
    if PurePosixPath(selected_path).name.lower() in DJANGO_MODULES:
        return {"status": "project_incomplete", "error": "Framework modules cannot be executed directly; provide the complete project entrypoint."}
    return {
        "status": None,
        "filename": selected_path,
        "image": DJANGO_RUNTIME_IMAGE if any(PurePosixPath(path).name.lower() in MANIFEST_NAMES for path in request.files) else STANDALONE_RUNTIME_IMAGE,
        "command": None,
        "working_directory": None,
        "check_type": "script_execution",
    }


def _execution_error(status: str, error: str, check_type: str) -> dict:
    return {
        "status": status,
        "check_type": check_type,
        "executed": False,
        "passed": False,
        "exit_code": None,
        "stdout": "",
        "stderr": error,
        "error": error,
        "error_type": "DependencyMissing" if status == "dependency_missing" else status,
    }


def _replace_execution_id(value: str | None, execution_id: str) -> str | None:
    return value.replace("{execution_id}", execution_id) if value else value


def _run_options(plan: dict, execution_id: str) -> dict:
    return {
        "image": plan["image"],
        "command": [part.replace("{execution_id}", execution_id) for part in plan["command"]] if plan["command"] else None,
        "working_directory": _replace_execution_id(plan["working_directory"], execution_id),
    }


def _execute_test_cases(request: CodeRequest, execution_id: str, plan: dict) -> dict:
    results = []
    options = _run_options(plan, execution_id)
    if plan["command"] is None:
        options = {}
    for index, test in enumerate(request.test_cases, 1):
        result = run_code(
            request.files,
            test.input,
            max(request.timeout, plan.get("minimum_timeout", 0)),
            f"{execution_id}-{index}",
            plan["filename"],
            **options,
        )
        actual = result["stdout"].strip()
        passed = result.get("status") == "completed" and result.get("exit_code") == 0 and (
            test.expected is None or actual == test.expected.strip()
        )
        results.append({
            "test_case": index,
            "input": test.input,
            "expected": test.expected,
            "actual": actual,
            "passed": passed,
            "status": result["status"],
            "error_type": result["error_type"],
            "stderr": result["stderr"],
        })

    total_passed = sum(item["passed"] for item in results)
    statuses = {item["status"] for item in results}
    if "unavailable" in statuses:
        status = "unavailable"
    elif "timeout" in statuses:
        status = "timeout"
    elif total_passed == len(results):
        status = "completed"
    else:
        status = "failed"
    return {
        "status": status,
        "check_type": "test_cases",
        "executed": all(item["status"] in {"completed", "failed", "timeout"} for item in results),
        "passed_execution": status == "completed",
        "total_tests": len(results),
        "passed": total_passed,
        "failed": sum(not item["passed"] for item in results),
        "exit_code": 0 if status == "completed" else 1,
        "results": results,
    }


@app.post("/execute")
def execute_code(request: CodeRequest):
    execution_id = str(uuid.uuid4())
    plan = _execution_plan(request)
    if plan["status"]:
        check_type = "django_check" if _django_project(request.files) else "script_execution"
        return _execution_error(plan["status"], plan["error"], check_type)

    if not request.test_cases:
        options = _run_options(plan, execution_id)
        if plan["command"] is None:
            options = {}
        timeout = (
            DJANGO_CHECK_TIMEOUT
            if plan["check_type"] == "django_check"
            else max(request.timeout, plan.get("minimum_timeout", 0))
        )
        result = run_code(request.files, request.stdin, timeout, execution_id, plan["filename"], **options)
        if (
            plan["check_type"] in {"static_compilation", "static_analysis"}
            and result.get("exit_code") == 127
            and re.search(r"(not found|no such file or directory)", result.get("stderr", ""), re.IGNORECASE)
        ):
            result.update({
                "status": "unavailable",
                "executed": False,
                "passed": False,
                "error_type": "ToolchainUnavailable",
                "error": result["stderr"][:MAX_OUTPUT],
            })
        if (
            plan.get("validator") == ".NET SDK"
            and "NuGet-Migrations" in result.get("stderr", "")
            and "Microsoft.DotNet.Configurer" in result.get("stderr", "")
        ):
            result.update({
                "status": "unavailable",
                "executed": False,
                "passed": False,
                "error_type": "ToolchainUnavailable",
                "error": (
                    ".NET SDK project builds are unavailable in the hardened "
                    "non-root sandbox because NuGet cannot initialize its "
                    "first-run mutex."
                ),
            })
        return {
            **result,
            "check_type": plan["check_type"],
            "validator": plan.get("validator"),
            "language": detect_language(list(request.files)),
        }
    return _execute_test_cases(request, execution_id, plan)