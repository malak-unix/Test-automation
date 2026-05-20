from __future__ import annotations

from pathlib import Path

from test_auto.agents.orchestrator import run_orchestrator_alone
from test_auto.agents.repo_analyzer import run_repo_analyzer_alone
from test_auto.graph.routing import route_after_orchestrator
from test_auto.graph.workflow import run_workflow


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_fake_django_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_django_repo"
    write_file(repo, "README.md", "# Fake Django REST project\n")
    write_file(
        repo,
        "requirements.txt",
        "django\ndjangorestframework\ndjangorestframework-simplejwt\npytest\n",
    )
    write_file(repo, "manage.py", "# placeholder\n")
    write_file(
        repo,
        "todo/urls.py",
        "\n".join(
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
    return repo


def test_integrated_workflow_runs_fake_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_repo(tmp_path)

    final_state = run_workflow(
        {
            "repo_path": str(fake_repo),
            "target_url": "http://localhost:8000",
            "user_preferences": {
                "test_types": ["api", "ui"],
                "execution_mode": "sequential",
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    run_id = final_state["run_id"]
    run_dir = Path("results") / "runs" / run_id
    assert run_id
    assert "repository_analyzer" in final_state["selected_agents"]
    assert final_state["orchestrator_decision"]
    assert final_state["project_info"]["framework"] == "Django REST Framework"
    assert final_state["discovered_endpoints"]
    assert final_state["indexed_documents"]
    assert (run_dir / "orchestrator_result.json").exists()
    assert (run_dir / "repo_analyzer_result.json").exists()
    assert (run_dir / "project_info.json").exists()
    assert (run_dir / "workflow_state.json").exists()


def test_route_after_orchestrator_valid_repo_path(tmp_path: Path) -> None:
    fake_repo = make_fake_django_repo(tmp_path)

    route = route_after_orchestrator(
        {
            "selected_agents": ["repository_analyzer"],
            "repo_path": str(fake_repo),
            "errors": [],
        }
    )

    assert route == "repo_analyzer"


def test_route_after_orchestrator_invalid_repo() -> None:
    route = route_after_orchestrator(
        {
            "selected_agents": ["repository_analyzer"],
            "repo_url": "",
            "repo_path": "",
            "errors": [
                {
                    "agent": "orchestrator",
                    "field": "repo_url",
                    "message": "missing repository input",
                }
            ],
        }
    )

    assert route == "end"


def test_integrated_workflow_invalid_repo_does_not_crash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    final_state = run_workflow(
        {
            "repo_url": "not-a-url",
            "target_url": "http://localhost:8000",
            "user_preferences": {"test_types": ["api"]},
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["run_id"]
    assert final_state["errors"]
    assert Path(final_state["workflow_state_path"]).exists()
    assert "project_info" not in final_state


def test_existing_standalone_agents_still_work(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_repo(tmp_path)

    orchestrator_result = run_orchestrator_alone(
        repo_url="https://github.com/Vitaee/DjangoRestAPI",
        target_url="http://localhost:8000",
        user_preferences={"test_types": ["api"], "execution_mode": "sequential"},
    )
    analyzer_result = run_repo_analyzer_alone(repo_path=str(fake_repo))

    assert orchestrator_result["orchestrator_decision"]
    assert analyzer_result["project_info"]["language"] == "Python"
