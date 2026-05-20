from __future__ import annotations

from pathlib import Path

from test_auto.agents.repo_analyzer import (
    analyze_repository,
    repo_analyzer_node,
    run_repo_analyzer_alone,
)
from test_auto.graph.repo_analyzer_workflow import run_repo_analyzer_workflow


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def create_fake_repo(root: Path) -> Path:
    repo = root / "fake_repo"
    write_file(repo, "README.md", "# Fake Todo API\n")
    write_file(
        repo,
        "requirements.txt",
        "django\ndjangorestframework\ndjangorestframework-simplejwt\npytest\n",
    )
    write_file(repo, "manage.py", "# django manage.py placeholder\n")
    write_file(
        repo,
        "todo/urls.py",
        '\n'.join(
            [
                "from django.urls import path",
                "urlpatterns = [",
                '    path("api/todos/", views.todo_list),',
                "]",
            ]
        ),
    )
    write_file(repo, "todo/views.py", "def todo_list(request): pass\n")
    write_file(repo, "templates/login.html", "<form>login</form>\n")
    write_file(repo, "tests/test_todo.py", "def test_todo(): assert True\n")
    return repo


def test_analyze_repository_local_fake_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    repo = create_fake_repo(tmp_path)

    result = analyze_repository(repo_path=str(repo))

    assert result["run_id"]
    assert result["project_info"]
    assert Path(result["agent_output_path"]).exists()
    assert Path(result["project_info_path"]).exists()
    assert isinstance(result["discovered_endpoints"], list)
    assert isinstance(result["indexed_documents"], list)


def test_repo_analyzer_node_returns_state_patch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    repo = create_fake_repo(tmp_path)

    update = repo_analyzer_node(
        {
            "run_id": "test_run",
            "repo_path": str(repo),
            "errors": [],
            "agent_logs": [],
        }
    )

    assert "project_info" in update
    assert "discovered_endpoints" in update
    assert "discovered_ui_flows" in update
    assert "indexed_documents" in update
    assert update["agent_logs"]


def test_run_repo_analyzer_alone(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    repo = create_fake_repo(tmp_path)

    result = run_repo_analyzer_alone(repo_path=str(repo))

    assert result["repo_path"] == str(repo.resolve())
    assert result["project_info"]["language"] == "Python"


def test_repo_analyzer_handles_missing_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = analyze_repository(repo_path=str(tmp_path / "missing"))

    assert result["errors"]
    assert result["agent_output"]["status"] == "error"


def test_repo_analyzer_mini_workflow_runs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    repo = create_fake_repo(tmp_path)

    final_state = run_repo_analyzer_workflow(
        {
            "run_id": "workflow_run",
            "repo_path": str(repo),
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["project_info"]["framework"] == "Django REST Framework"
    assert final_state["discovered_endpoints"]
    assert final_state["indexed_documents"]
