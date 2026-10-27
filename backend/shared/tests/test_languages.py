import pytest

from shared.languages import (
    LANGUAGE_ADAPTERS,
    PLATFORM_ADAPTERS,
    adapter_for_language,
    detect_language,
    language_for_path,
    source_files,
    validate_project_path,
)


@pytest.mark.parametrize(
    ("path", "language"),
    [
        ("main.py", "python"),
        ("src/main.jsx", "javascript"),
        ("src/main.tsx", "typescript"),
        ("Main.java", "java"),
        ("main.c", "c"),
        ("main.cpp", "cpp"),
        ("main.go", "go"),
        ("Program.cs", "csharp"),
    ],
)
def test_language_for_supported_source_paths(path, language):
    assert language_for_path(path) == language


def test_detect_language_allows_js_ts_and_c_cpp_headers_in_one_project():
    assert detect_language(["index.js"]) == "javascript"
    assert detect_language(["index.ts"]) == "typescript"
    assert detect_language(["index.js", "src/types.ts"]) == "typescript"
    assert detect_language(["main.cpp", "header.h"]) == "cpp"
    assert detect_language(["main.c", "header.h"]) == "c"


def test_detect_language_rejects_unrelated_mixed_languages():
    with pytest.raises(ValueError, match="one programming language"):
        detect_language(["main.py", "main.js"])


def test_project_paths_reject_traversal_and_accept_supported_manifests():
    with pytest.raises(ValueError, match="relative"):
        validate_project_path("../main.py")
    assert validate_project_path("src/main.go") == "src/main.go"
    assert validate_project_path("package.json") == "package.json"
    assert validate_project_path("MyApp.csproj") == "MyApp.csproj"


def test_registry_distinguishes_supported_languages_and_dotnet_platform():
    assert set(LANGUAGE_ADAPTERS) == {
        "python", "javascript", "typescript", "java", "c", "cpp", "go", "csharp"
    }
    assert adapter_for_language("python")["support"] == "full"
    assert all(
        adapter_for_language(language)["support"] == "partial"
        for language in LANGUAGE_ADAPTERS
        if language != "python"
    )
    assert PLATFORM_ADAPTERS["dotnet"]["language"] == "csharp"


def test_source_files_excludes_manifests():
    assert source_files({
        "main.py": "print('ok')",
        "requirements.txt": "pytest",
        "package.json": "{}",
    }) == {"main.py": "print('ok')"}
