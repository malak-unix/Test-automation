"""Deterministic local repository inspection tools."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from test_auto.shared.utils import ensure_directory


IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    "media",
    "staticfiles",
}
TEXT_EXTENSIONS = {
    ".cfg",
    ".css",
    ".gradle",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".rst",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_FILE_NAMES = {
    "dockerfile",
    "makefile",
    "manage.py",
    "pom.xml",
    "pytest.ini",
    "requirements.txt",
}


def is_probably_git_url(value: str) -> bool:
    """Return True for common GitHub HTTPS and SSH repository URLs."""

    if not value:
        return False
    patterns = [
        r"^https://github\.com/[^/\s]+/[^/\s]+(?:\.git)?/?$",
        r"^git@github\.com:[^/\s]+/[^/\s]+\.git$",
    ]
    return any(re.match(pattern, value.strip()) for pattern in patterns)


def clone_repository(repo_url: str, run_id: str, results_dir: str = "results") -> dict[str, Any]:
    """Clone a Git repository into results/runs/<run_id>/repo."""

    destination = Path(results_dir) / "runs" / run_id / "repo"
    if not is_probably_git_url(repo_url):
        return {
            "status": "error",
            "repo_path": "",
            "details": "Invalid or unsupported Git URL.",
            "error": "repo_url must be a GitHub HTTPS or SSH URL.",
        }
    if destination.exists():
        return {
            "status": "success",
            "repo_path": str(destination),
            "details": "Repository destination already exists; clone skipped.",
            "error": None,
        }

    ensure_directory(destination.parent)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(destination)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            "status": "success",
            "repo_path": str(destination),
            "details": "Repository cloned successfully.",
            "error": None,
        }
    except (subprocess.SubprocessError, OSError) as error:
        return {
            "status": "error",
            "repo_path": str(destination),
            "details": "Repository clone failed.",
            "error": str(error),
        }


def resolve_repo_path(
    repo_url: str | None,
    repo_path: str | None,
    run_id: str,
) -> dict[str, Any]:
    """Resolve an existing local repo path or clone a supported Git URL."""

    if repo_path:
        path = Path(repo_path).expanduser().resolve()
        if path.exists() and path.is_dir():
            return {
                "status": "success",
                "repo_path": str(path),
                "details": "Using existing local repository path.",
                "error": None,
            }
        return {
            "status": "error",
            "repo_path": str(path),
            "details": "Local repository path does not exist.",
            "error": "repo_path does not exist or is not a directory.",
        }

    if repo_url and is_probably_git_url(repo_url):
        return clone_repository(repo_url, run_id)

    return {
        "status": "error",
        "repo_path": "",
        "details": "No usable local repository path or Git URL was provided.",
        "error": "Provide repo_path or a supported repo_url.",
    }


def _is_ignored(relative_path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in relative_path.parts)


def _is_text_like(path: Path) -> bool:
    if path.name.lower() in TEXT_FILE_NAMES:
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


def list_project_files(repo_path: str, max_files: int = 500) -> list[str]:
    """Recursively list stable text/code/config/doc-like project files."""

    root = Path(repo_path).resolve()
    if not root.exists() or not root.is_dir():
        return []

    results: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if _is_ignored(relative) or not _is_text_like(path):
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
        except OSError:
            continue
        results.append(relative.as_posix())
        if len(results) >= max_files:
            break

    return sorted(results)


def read_text_file(repo_path: str, relative_path: str, max_chars: int = 20000) -> str:
    """Read a repository text file without allowing path traversal."""

    root = Path(repo_path).resolve()
    target = (root / relative_path).resolve()
    try:
        common = os.path.commonpath([str(root), str(target)])
    except ValueError:
        return ""
    if common != str(root) or not target.is_file():
        return ""
    try:
        data = target.read_bytes()
    except OSError:
        return ""
    if b"\x00" in data[:2048]:
        return ""
    try:
        return data[:max_chars].decode("utf-8", errors="ignore")
    except UnicodeError:
        return ""


def _combined_text(repo_path: str, files: list[str], selected: list[str]) -> str:
    chunks = [read_text_file(repo_path, path, max_chars=10000) for path in selected if path in files]
    return "\n".join(chunks).lower()


def _read_package_json(repo_path: str, files: list[str]) -> dict[str, Any]:
    if "package.json" not in files:
        return {}
    try:
        return json.loads(read_text_file(repo_path, "package.json"))
    except json.JSONDecodeError:
        return {}


def detect_language_and_framework(files: list[str], repo_path: str) -> dict[str, Any]:
    """Detect language, framework, package manager, tests, auth, and risks."""

    lower_files = [path.lower() for path in files]
    package_json = _read_package_json(repo_path, files)
    dependency_blob = " ".join(
        str(value).lower()
        for section in ("dependencies", "devDependencies")
        for value in package_json.get(section, {}).keys()
    )
    config_text = _combined_text(
        repo_path,
        files,
        [
            "requirements.txt",
            "pyproject.toml",
            "Pipfile",
            "package.json",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
        ],
    )
    sample_code_files = [
        path
        for path in files
        if Path(path).suffix.lower() in {".py", ".js", ".ts", ".jsx", ".tsx", ".java"}
    ][:50]
    code_text = _combined_text(repo_path, files, sample_code_files)
    all_text = f"{config_text}\n{code_text}"

    python_score = sum(path.endswith(".py") for path in lower_files) + int("manage.py" in lower_files)
    js_score = sum(path.endswith((".js", ".jsx", ".ts", ".tsx")) for path in lower_files)
    java_score = sum(path.endswith(".java") for path in lower_files) + int(
        "pom.xml" in lower_files or "build.gradle" in lower_files
    )

    if python_score >= js_score and python_score >= java_score and python_score > 0:
        language = "Python"
    elif js_score >= java_score and js_score > 0:
        language = "JavaScript/TypeScript"
    elif java_score > 0:
        language = "Java"
    else:
        language = "Unknown"

    framework = "Unknown"
    if "djangorestframework" in all_text or "rest_framework" in all_text:
        framework = "Django REST Framework"
    elif "manage.py" in lower_files or any(path.endswith("settings.py") or path.endswith("urls.py") for path in lower_files):
        framework = "Django"
    elif "fastapi(" in all_text or "from fastapi" in all_text:
        framework = "FastAPI"
    elif "flask(" in all_text or "from flask" in all_text:
        framework = "Flask"
    elif "spring-boot" in all_text:
        framework = "Spring Boot"
    elif "express" in dependency_blob:
        framework = "Express"
    elif "react" in dependency_blob:
        framework = "React"

    package_manager = None
    if "requirements.txt" in lower_files:
        package_manager = "pip"
    elif "pyproject.toml" in lower_files:
        package_manager = "pyproject"
    elif "package-lock.json" in lower_files or "package.json" in lower_files:
        package_manager = "npm"
    elif "yarn.lock" in lower_files:
        package_manager = "yarn"
    elif "pnpm-lock.yaml" in lower_files:
        package_manager = "pnpm"
    elif "pom.xml" in lower_files:
        package_manager = "maven"
    elif "build.gradle" in lower_files or "build.gradle.kts" in lower_files:
        package_manager = "gradle"

    test_framework = None
    if "pytest" in all_text or "pytest.ini" in lower_files or any(path.startswith("tests/") for path in lower_files):
        test_framework = "pytest"
    elif "jest" in dependency_blob:
        test_framework = "jest"
    elif "junit" in all_text:
        test_framework = "JUnit"

    auth_type = "None"
    if any(token in all_text for token in ["simplejwt", "pyjwt", "jwt", "bearer"]):
        auth_type = "JWT"
    elif "basicauth" in all_text or "basic authentication" in all_text:
        auth_type = "Basic"
    elif "session" in all_text or "csrf" in all_text:
        auth_type = "Session"
    elif "auth" in all_text:
        auth_type = "Unknown"

    risks: list[str] = []
    if language == "Unknown":
        risks.append("Could not confidently detect the main language.")
    if framework == "Unknown":
        risks.append("Could not confidently detect the web framework.")

    return {
        "language": language,
        "framework": framework,
        "package_manager": package_manager,
        "test_framework": test_framework,
        "auth_type": auth_type,
        "risks": risks,
    }


def find_candidate_docs(files: list[str]) -> list[str]:
    """Return documentation files useful for later RAG."""

    candidates: list[str] = []
    for path in files:
        lower = path.lower()
        name = Path(lower).name
        if name in {"readme.md", "readme.rst", "api.md"}:
            candidates.append(path)
        elif lower.startswith("docs/"):
            candidates.append(path)
        elif name in {
            "openapi.yaml",
            "openapi.yml",
            "openapi.json",
            "swagger.yaml",
            "swagger.yml",
            "swagger.json",
        }:
            candidates.append(path)
        elif "documentation" in lower and Path(lower).suffix in {".md", ".rst", ".txt"}:
            candidates.append(path)
    return sorted(dict.fromkeys(candidates))


def find_test_dirs(files: list[str]) -> list[str]:
    """Return files and directories that indicate test coverage."""

    candidates: list[str] = []
    for path in files:
        lower = path.lower()
        name = Path(lower).name
        if lower.startswith("tests/"):
            candidates.append("tests")
        if "/__tests__/" in lower or lower.startswith("__tests__/"):
            candidates.append("__tests__")
        if name.startswith("test_") and name.endswith(".py"):
            candidates.append(path)
        elif name.endswith("_test.py"):
            candidates.append(path)
        elif name.endswith((".spec.ts", ".test.ts", ".spec.tsx", ".test.tsx")):
            candidates.append(path)
        elif name in {"pytest.ini", "conftest.py"}:
            candidates.append(path)
    return sorted(dict.fromkeys(candidates))


def find_candidate_api_files(files: list[str]) -> list[str]:
    """Return files likely to define API routes or controllers."""

    names = {"urls.py", "views.py", "routers.py", "routes.py", "api.py", "main.py", "app.py", "serializers.py"}
    candidates: list[str] = []
    for path in files:
        lower = path.lower()
        name = Path(lower).name
        if name in names:
            candidates.append(path)
        elif any(part in lower.split("/") for part in ["controllers", "routes", "viewsets"]):
            candidates.append(path)
    return sorted(dict.fromkeys(candidates))


def find_candidate_ui_files(files: list[str]) -> list[str]:
    """Return files likely to define UI screens or components."""

    candidates: list[str] = []
    for path in files:
        lower = path.lower()
        name = Path(lower).name
        if lower.startswith(("templates/", "static/", "frontend/", "src/pages/", "src/components/")):
            candidates.append(path)
        elif name.endswith((".html", ".tsx", ".jsx")):
            candidates.append(path)
        elif name in {"login.html", "register.html"}:
            candidates.append(path)
    return sorted(dict.fromkeys(candidates))


def _normalize_route(route: str) -> str:
    route = route.strip()
    if not route.startswith("/"):
        route = "/" + route
    return route


def _endpoint_name(path: str) -> str:
    clean = path.strip("/").replace("<", "").replace(">", "")
    return clean.replace("/", "_") or "root"


def discover_python_endpoints(repo_path: str, candidate_api_files: list[str]) -> list[dict[str, Any]]:
    """Heuristically parse common Python route declarations."""

    endpoints: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for relative_path in candidate_api_files:
        if Path(relative_path).suffix.lower() != ".py":
            continue
        text = read_text_file(repo_path, relative_path)
        for line_number, line in enumerate(text.splitlines(), start=1):
            django_match = re.search(r"\b(?:path|re_path)\(\s*[rRuUbBfF]*[\"']([^\"']+)[\"']", line)
            if django_match:
                path = _normalize_route(django_match.group(1))
                key = ("UNKNOWN", path, relative_path)
                if key not in seen:
                    seen.add(key)
                    endpoints.append(
                        {
                            "name": _endpoint_name(path),
                            "method": "UNKNOWN",
                            "path": path,
                            "source_file": relative_path,
                            "line_number": line_number,
                            "confidence": 0.7,
                        }
                    )

            fastapi_match = re.search(
                r"@\w+\.(get|post|put|delete|patch)\(\s*[rRuUbBfF]*[\"']([^\"']+)[\"']",
                line,
                re.IGNORECASE,
            )
            if fastapi_match:
                method = fastapi_match.group(1).upper()
                path = _normalize_route(fastapi_match.group(2))
                key = (method, path, relative_path)
                if key not in seen:
                    seen.add(key)
                    endpoints.append(
                        {
                            "name": _endpoint_name(path),
                            "method": method,
                            "path": path,
                            "source_file": relative_path,
                            "line_number": line_number,
                            "confidence": 0.8,
                        }
                    )

            flask_match = re.search(
                r"@\w+\.route\(\s*[rRuUbBfF]*[\"']([^\"']+)[\"'](?P<args>[^)]*)\)",
                line,
                re.IGNORECASE,
            )
            if flask_match:
                path = _normalize_route(flask_match.group(1))
                args = flask_match.group("args")
                methods = re.findall(r"[\"'](GET|POST|PUT|DELETE|PATCH)[\"']", args, re.IGNORECASE)
                if not methods:
                    methods = ["GET"]
                for method_value in methods:
                    method = method_value.upper()
                    key = (method, path, relative_path)
                    if key in seen:
                        continue
                    seen.add(key)
                    endpoints.append(
                        {
                            "name": _endpoint_name(path),
                            "method": method,
                            "path": path,
                            "source_file": relative_path,
                            "line_number": line_number,
                            "confidence": 0.75,
                        }
                    )

    return endpoints


def discover_ui_flows(files: list[str]) -> list[dict[str, Any]]:
    """Heuristically detect UI flows from file names and paths."""

    flow_keywords = {
        "login": "authentication",
        "register": "authentication",
        "signup": "authentication",
        "dashboard": "navigation",
        "todo": "task_management",
        "todos": "task_management",
        "task": "task_management",
        "create": "crud",
        "edit": "crud",
        "delete": "crud",
    }
    flows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for path in files:
        lower = path.lower()
        for keyword, flow_type in flow_keywords.items():
            if keyword in lower:
                name = "todo" if keyword == "todos" else keyword
                key = (name, path)
                if key in seen:
                    continue
                seen.add(key)
                flows.append(
                    {
                        "name": name,
                        "source_file": path,
                        "flow_type": flow_type,
                        "confidence": 0.6,
                    }
                )
    return flows


def _find_source_dirs(files: list[str]) -> list[str]:
    candidates = set()
    for path in files:
        parts = path.split("/")
        if not parts or parts[0] in {"tests", "__tests__"}:
            continue
        if parts[0] in {"src", "app", "apps", "backend", "frontend"}:
            candidates.add(parts[0])
        elif Path(path).suffix.lower() in {".py", ".js", ".ts", ".jsx", ".tsx", ".java"} and len(parts) > 1:
            candidates.add(parts[0])
    return sorted(candidates)


def build_project_info(repo_path: str, files: list[str]) -> dict[str, Any]:
    """Combine repository detection heuristics into compact project metadata."""

    detected = detect_language_and_framework(files, repo_path)
    candidate_docs = find_candidate_docs(files)
    test_dirs = find_test_dirs(files)
    candidate_api_files = find_candidate_api_files(files)
    candidate_ui_files = find_candidate_ui_files(files)
    risks = list(detected.get("risks", []))
    if not test_dirs:
        risks.append("No obvious test files or test configuration were found.")

    return {
        "language": detected["language"],
        "framework": detected["framework"],
        "test_framework": detected.get("test_framework"),
        "has_api": bool(candidate_api_files),
        "has_ui": bool(candidate_ui_files),
        "auth_type": detected.get("auth_type"),
        "package_manager": detected.get("package_manager"),
        "source_dirs": _find_source_dirs(files),
        "test_dirs": test_dirs,
        "candidate_docs": candidate_docs,
        "candidate_api_files": candidate_api_files,
        "candidate_ui_files": candidate_ui_files,
        "risks": risks,
    }


def select_indexed_documents(project_info: dict[str, Any]) -> list[dict[str, str]]:
    """Select candidate files for future RAG without building embeddings."""

    indexed: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(paths: list[str], doc_type: str, reason: str) -> None:
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            indexed.append({"path": path, "type": doc_type, "reason": reason})

    add(project_info.get("candidate_docs", []), "doc", "candidate documentation")
    add(project_info.get("candidate_api_files", []), "api", "candidate API route file")
    add(project_info.get("test_dirs", []), "test", "candidate test evidence")
    add(project_info.get("candidate_ui_files", []), "ui", "candidate UI file")

    return indexed
