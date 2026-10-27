import pytest

from app.main import CodeRequest, _execution_plan


@pytest.mark.parametrize(
    ("filename", "code", "command"),
    [
        ("main.js", 'console.log("ok");', "node"),
        ("main.ts", 'const value: string = "ok";', "tsc"),
        ("Main.java", "public class Main { public static void main(String[] args) {} }", "javac"),
        ("main.c", "int main(void) { return 0; }", "gcc"),
        ("main.cpp", "int main() { return 0; }", "g++"),
        ("main.go", "package main\nfunc main() {}", "go run"),
        ("Program.cs", "public class Program { public static void Main() {} }", "mcs"),
    ],
)
def test_supported_languages_have_isolated_execution_plans(filename, code, command):
    request = CodeRequest(filename=filename, code=code, files={filename: code})

    plan = _execution_plan(request)

    assert plan["status"] is None
    assert plan["check_type"] == "compile_and_execute"
    assert command in " ".join(plan["command"])
    assert plan["minimum_timeout"] == (45 if filename.endswith(".go") else 0)


def test_mixed_unrelated_languages_are_rejected():
    with pytest.raises(ValueError, match="one programming language"):
        CodeRequest(
            filename="main.py",
            code="print('ok')",
            files={"main.py": "print('ok')", "main.js": 'console.log("ok")'},
        )


@pytest.mark.parametrize(
    ("filename", "code", "checker"),
    [
        ("main.js", "const value = 1;\n", "node --check"),
        ("main.ts", "const value: number = 1;\n", "tsc --noEmit"),
        ("Main.java", "class Main {}\n", "javac -Xlint:all"),
        ("main.c", "int main(void) { return 0; }\n", "gcc -std=c11"),
        ("main.cpp", "int main() { return 0; }\n", "g++ -std=c++17"),
        ("main.go", "package main\nfunc main() {}\n", "go build"),
        ("Program.cs", "public class Program {}\n", "mcs -r:System.Data -target:library"),
    ],
)
def test_validation_only_uses_language_compiler_without_running_user_program(filename, code, checker):
    request = CodeRequest(
        filename=filename,
        code=code,
        files={filename: code},
        validation_only=True,
    )

    plan = _execution_plan(request)

    assert plan["check_type"] == "static_compilation"
    assert checker in " ".join(plan["command"])
    assert "exec " not in " ".join(plan["command"])


def test_dotnet_project_uses_dotnet_sdk_build():
    project = {
        "Program.cs": "public class Program { public static void Main() {} }\n",
        "App.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>",
    }
    request = CodeRequest(
        filename="Program.cs",
        code=project["Program.cs"],
        files=project,
        validation_only=True,
    )

    plan = _execution_plan(request)

    assert plan["check_type"] == "static_compilation"
    assert ".NET SDK" == plan["validator"]
    assert "dotnet build" in " ".join(plan["command"])


@pytest.mark.parametrize(
    ("filename", "code", "analyzer"),
    [
        ("main.js", "const unused = 1;\n", "eslint"),
        ("main.ts", "const value: number = 1;\n", "tsc --noEmit"),
        ("Main.java", "class Main {}\n", "checkstyle"),
        ("main.c", "int main(void) { return 0; }\n", "cppcheck"),
        ("main.cpp", "int main() { return 0; }\n", "cppcheck"),
        ("main.go", "package main\nfunc main() {}\n", "go vet"),
        ("Program.cs", "public class Program {}\n", "mcs -r:System.Data -warn:4"),
    ],
)
def test_language_analysis_uses_real_static_analyzer(filename, code, analyzer):
    request = CodeRequest(
        filename=filename,
        code=code,
        files={filename: code},
        analysis_only=True,
    )

    plan = _execution_plan(request)

    assert plan["check_type"] == "static_analysis"
    assert analyzer in " ".join(plan["command"])
    if filename == "main.js":
        assert "--format json" in " ".join(plan["command"])


def test_javascript_analysis_includes_browser_globals_when_browser_apis_are_used():
    code = 'document.getElementById("profile").textContent = "ready";\n'
    request = CodeRequest(
        filename="main.js",
        code=code,
        files={"main.js": code},
        analysis_only=True,
    )

    plan = _execution_plan(request)
    command = " ".join(plan["command"])

    assert "--global document" in command
    assert "--global XMLHttpRequest" in command
    assert "--global require" in command


def test_javascript_analysis_does_not_enable_browser_globals_for_node_only_source():
    code = 'const value = process.env.VALUE;\nconsole.log(value);\n'
    request = CodeRequest(
        filename="main.js",
        code=code,
        files={"main.js": code},
        analysis_only=True,
    )

    plan = _execution_plan(request)

    assert "--global process" in " ".join(plan["command"])
    assert "--global document" not in " ".join(plan["command"])


def test_javascript_analysis_detects_browser_package_manifest():
    code = 'console.log("browser app");\n'
    request = CodeRequest(
        filename="main.js",
        code=code,
        files={
            "main.js": code,
            "package.json": '{"dependencies":{"react":"18.0.0"}}',
        },
        analysis_only=True,
    )

    plan = _execution_plan(request)

    assert "--global document" in " ".join(plan["command"])


def test_dotnet_analysis_uses_sdk_build():
    project = {
        "Program.cs": "public class Program {}\n",
        "App.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>",
    }
    request = CodeRequest(
        filename="Program.cs",
        code=project["Program.cs"],
        files=project,
        analysis_only=True,
    )

    plan = _execution_plan(request)

    assert plan["check_type"] == "static_analysis"
    assert plan["validator"] == ".NET SDK"
    assert "dotnet build" in " ".join(plan["command"])


@pytest.mark.parametrize(
    ("mode", "expected_command"),
    [
        ("validation_only", "go build -o /tmp/go-validation"),
        ("analysis_only", "go vet /tmp/go-src/*.go"),
        ("execution", "go run /tmp/go-src/*.go"),
    ],
)
def test_go_test_filenames_are_staged_as_regular_source_files(mode, expected_command):
    request = CodeRequest(
        filename="go_test.go",
        code="package main\nfunc main() {}\n",
        files={"go_test.go": "package main\nfunc main() {}\n"},
        validation_only=mode == "validation_only",
        analysis_only=mode == "analysis_only",
    )

    plan = _execution_plan(request)

    command = " ".join(plan["command"])
    assert plan["status"] is None
    assert expected_command in command
    assert "source-${index}.go" in command or "main.go" in command


def test_go_execution_stages_all_source_files_including_test_suffixes():
    files = {
        "go_test.go": "package main\nfunc main() { println(message()) }\n",
        "helper_test.go": "package main\nfunc message() string { return \"ok\" }\n",
    }
    request = CodeRequest(
        filename="go_test.go",
        code=files["go_test.go"],
        files=files,
    )

    plan = _execution_plan(request)
    command = " ".join(plan["command"])

    assert plan["status"] is None
    assert "while [ \"$#\" -gt 1 ]" in command
    assert "go run /tmp/go-src/*.go" in command
    assert "/sandbox/{execution_id}/go_test.go" in command
    assert "/sandbox/{execution_id}/helper_test.go" in command


@pytest.mark.parametrize(
    ("mode", "expected_command"),
    [
        ("validation_only", "mcs -r:System.Data -target:library"),
        ("analysis_only", "mcs -r:System.Data -warn:4"),
        ("execution", "mcs -r:System.Data -out:/tmp/program.exe"),
    ],
)
def test_mono_validation_references_standard_system_data_assembly(mode, expected_command):
    request = CodeRequest(
        filename="Program.cs",
        code="using System.Data;\nclass Program {}\n",
        files={"Program.cs": "using System.Data;\nclass Program {}\n"},
        validation_only=mode == "validation_only",
        analysis_only=mode == "analysis_only",
    )

    plan = _execution_plan(request)

    assert plan["status"] is None
    assert expected_command in " ".join(plan["command"])
