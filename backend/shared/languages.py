from pathlib import PurePosixPath
from typing import Literal, TypedDict


SupportLevel = Literal["full", "partial", "unsupported"]


class LanguageAdapter(TypedDict):
    label: str
    support: SupportLevel
    validator: str
    analysis: str
    platform: str | None


LANGUAGE_ADAPTERS: dict[str, LanguageAdapter] = {
    "python": {
        "label": "Python",
        "support": "full",
        "validator": "ast+flake8",
        "analysis": "ruff+pylint+radon+ast",
        "platform": None,
    },
    "java": {
        "label": "Java",
        "support": "partial",
        "validator": "javac-xlint",
        "analysis": "checkstyle+javac",
        "platform": "JDK",
    },
    "javascript": {
        "label": "JavaScript",
        "support": "partial",
        "validator": "node-syntax-check",
        "analysis": "eslint",
        "platform": "Node.js",
    },
    "typescript": {
        "label": "TypeScript",
        "support": "partial",
        "validator": "typescript-compiler",
        "analysis": "tsc-noemit",
        "platform": "TypeScript",
    },
    "c": {
        "label": "C",
        "support": "partial",
        "validator": "gcc-fsyntax-only",
        "analysis": "cppcheck",
        "platform": "GCC",
    },
    "cpp": {
        "label": "C++",
        "support": "partial",
        "validator": "g++-fsyntax-only",
        "analysis": "cppcheck",
        "platform": "G++",
    },
    "go": {
        "label": "Go",
        "support": "partial",
        "validator": "go-build",
        "analysis": "go-vet",
        "platform": "Go toolchain",
    },
    "csharp": {
        "label": "C#",
        "support": "partial",
        "validator": "mono-or-dotnet-compiler",
        "analysis": "mono-warnings-or-dotnet-build",
        "platform": "Mono or .NET SDK",
    },
}

PLATFORM_ADAPTERS = {
    "dotnet": {
        "label": ".NET project",
        "language": "csharp",
        "project_extension": ".csproj",
        "support": "partial",
    }
}


SOURCE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hh": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".go": "go",
    ".cs": "csharp",
}

SOURCE_LANGUAGES = frozenset(SOURCE_EXTENSIONS.values())
PROJECT_MANIFESTS = frozenset({
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "go.sum",
    "global.json",
    "nuget.config",
})
PROJECT_EXTENSIONS = frozenset({".csproj", ".sln"})


def language_for_path(path: str) -> str | None:
    return SOURCE_EXTENSIONS.get(PurePosixPath(path).suffix.lower())


def is_source_path(path: str) -> bool:
    return language_for_path(path) is not None


def is_project_manifest(path: str) -> bool:
    candidate = PurePosixPath(path)
    return (
        candidate.name.lower() in PROJECT_MANIFESTS
        or candidate.suffix.lower() in PROJECT_EXTENSIONS
    )


def adapter_for_language(language: str) -> LanguageAdapter | None:
    return LANGUAGE_ADAPTERS.get(language.strip().lower())


def detect_language(paths: list[str] | tuple[str, ...] | set[str]) -> str | None:
    languages = {language for path in paths if (language := language_for_path(path))}
    if not languages:
        return None
    if "typescript" in languages and languages <= {"javascript", "typescript"}:
        return "typescript"
    if languages <= {"c", "cpp"}:
        return "cpp" if "cpp" in languages else "c"
    if len(languages) == 1:
        return next(iter(languages))
    raise ValueError(
        "A project may contain one programming language per analysis; "
        f"received {', '.join(sorted(languages))}."
    )


def source_files(files: dict[str, str]) -> dict[str, str]:
    return {path: content for path, content in files.items() if is_source_path(path)}


def validate_project_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    has_windows_drive = bool(path.parts) and len(path.parts[0]) == 2 and path.parts[0][1] == ":"
    if not normalized or path.is_absolute() or has_windows_drive or ".." in path.parts:
        raise ValueError("file path must be relative and stay inside the project")
    if not is_source_path(normalized) and not is_project_manifest(normalized):
        raise ValueError("unsupported source file or project manifest")
    return "/".join(path.parts)
