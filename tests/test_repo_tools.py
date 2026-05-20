from __future__ import annotations

from pathlib import Path

from test_auto.tools.repo_tools import (
    build_project_info,
    detect_language_and_framework,
    discover_python_endpoints,
    discover_ui_flows,
    find_candidate_api_files,
    find_candidate_docs,
    find_test_dirs,
    list_project_files,
    read_text_file,
    select_indexed_documents,
)


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_list_project_files_ignores_noise(tmp_path: Path) -> None:
    write_file(tmp_path, ".git/config")
    write_file(tmp_path, "node_modules/lib.js")
    write_file(tmp_path, "__pycache__/x.pyc")
    write_file(tmp_path, "README.md")
    write_file(tmp_path, "manage.py")

    files = list_project_files(str(tmp_path))

    assert "README.md" in files
    assert "manage.py" in files
    assert ".git/config" not in files
    assert "node_modules/lib.js" not in files
    assert "__pycache__/x.pyc" not in files


def test_detect_django_rest_framework(tmp_path: Path) -> None:
    write_file(tmp_path, "manage.py")
    write_file(tmp_path, "requirements.txt", "django\ndjangorestframework\npytest\n")
    files = list_project_files(str(tmp_path))

    detected = detect_language_and_framework(files, str(tmp_path))

    assert detected["language"] == "Python"
    assert "Django" in detected["framework"]


def test_find_candidate_docs() -> None:
    files = ["README.md", "docs/api.md", "src/app.py"]

    docs = find_candidate_docs(files)

    assert "README.md" in docs
    assert "docs/api.md" in docs


def test_find_test_dirs() -> None:
    files = ["tests/test_api.py", "pytest.ini", "src/app.py"]

    tests = find_test_dirs(files)

    assert "tests" in tests
    assert "tests/test_api.py" in tests
    assert "pytest.ini" in tests


def test_find_candidate_api_files() -> None:
    files = ["todo/urls.py", "todo/views.py", "README.md"]

    api_files = find_candidate_api_files(files)

    assert "todo/urls.py" in api_files
    assert "todo/views.py" in api_files


def test_discover_python_endpoints_django_path(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "todo/urls.py",
        '\n'.join(
            [
                "from django.urls import path",
                "urlpatterns = [",
                '    path("api/todos/", views.todo_list),',
                '    path("api/todos/<int:pk>/", views.todo_detail),',
                "]",
            ]
        ),
    )

    endpoints = discover_python_endpoints(str(tmp_path), ["todo/urls.py"])
    paths = {endpoint["path"] for endpoint in endpoints}

    assert "/api/todos/" in paths
    assert "/api/todos/<int:pk>/" in paths


def test_discover_python_endpoints_fastapi(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "main.py",
        '\n'.join(
            [
                'from fastapi import FastAPI',
                'app = FastAPI()',
                '@app.get("/items")',
                "def list_items(): pass",
                '@app.post("/items")',
                "def create_item(): pass",
            ]
        ),
    )

    endpoints = discover_python_endpoints(str(tmp_path), ["main.py"])
    methods = {(endpoint["method"], endpoint["path"]) for endpoint in endpoints}

    assert ("GET", "/items") in methods
    assert ("POST", "/items") in methods


def test_discover_ui_flows() -> None:
    files = [
        "templates/login.html",
        "templates/register.html",
        "templates/todos.html",
    ]

    flows = discover_ui_flows(files)
    names = {flow["name"] for flow in flows}

    assert "login" in names
    assert "register" in names
    assert "todo" in names


def test_select_indexed_documents() -> None:
    project_info = {
        "candidate_docs": ["README.md", "docs/api.md"],
        "candidate_api_files": ["todo/urls.py"],
        "test_dirs": ["tests", "pytest.ini"],
        "candidate_ui_files": ["templates/login.html"],
    }

    indexed_documents = select_indexed_documents(project_info)
    indexed_paths = {item["path"] for item in indexed_documents}

    assert "README.md" in indexed_paths
    assert "todo/urls.py" in indexed_paths
    assert "tests" in indexed_paths
    assert "templates/login.html" in indexed_paths


def test_read_text_file_prevents_path_traversal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(tmp_path, "secret.txt", "secret")

    content = read_text_file(str(repo), "../secret.txt")

    assert content == ""


def test_build_project_info_combines_candidates(tmp_path: Path) -> None:
    write_file(tmp_path, "README.md")
    write_file(tmp_path, "requirements.txt", "django\ndjangorestframework\npytest\n")
    write_file(tmp_path, "manage.py")
    write_file(tmp_path, "todo/urls.py")
    write_file(tmp_path, "templates/login.html")
    write_file(tmp_path, "tests/test_todo.py")
    files = list_project_files(str(tmp_path))

    project_info = build_project_info(str(tmp_path), files)

    assert project_info["has_api"] is True
    assert project_info["has_ui"] is True
    assert "README.md" in project_info["candidate_docs"]
