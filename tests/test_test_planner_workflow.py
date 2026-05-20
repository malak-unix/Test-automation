from __future__ import annotations

from pathlib import Path

from test_auto.graph.test_planner_workflow import run_test_planner_workflow
from test_auto.graph.workflow import run_workflow


def fake_state() -> dict:
    return {
        "run_id": "planner_workflow_test",
        "project_info": {
            "language": "Python",
            "framework": "Django REST Framework",
            "has_api": True,
            "has_ui": True,
            "auth_type": "JWT",
        },
        "discovered_endpoints": [
            {
                "method": "UNKNOWN",
                "path": "/api/todos/",
                "source_file": "todo/urls.py",
            }
        ],
        "discovered_ui_flows": [
            {
                "name": "login",
                "source_file": "templates/login.html",
                "flow_type": "authentication",
            }
        ],
        "retrieved_context": [
            {
                "source_path": "README.md",
                "content": "JWT authentication is required for Todo CRUD API operations.",
                "score": 0.9,
                "reason": "JWT and CRUD evidence",
                "chunk_type": "doc",
            }
        ],
        "user_preferences": {"test_types": ["api", "ui"], "use_llm": False},
        "missing_information": [],
        "errors": [],
        "agent_logs": [],
    }


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_fake_django_rest_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_main_still_rag"
    write_file(repo, "README.md", "# Todo API\nJWT authentication protects Todo CRUD API routes.\n")
    write_file(repo, "requirements.txt", "django\ndjangorestframework\ndjangorestframework-simplejwt\n")
    write_file(repo, "manage.py", "# placeholder\n")
    write_file(repo, "todo/urls.py", 'path("api/todos/", views.todo_list)\n')
    write_file(repo, "todo/views.py", "def todo_list(request): pass\n")
    write_file(repo, "templates/login.html", "<form>login</form>\n")
    return repo


def test_test_planner_workflow_fake_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    final_state = run_test_planner_workflow(fake_state())

    assert final_state["test_plan"]
    assert final_state["test_plan_path"]
    assert final_state["planner_model_info"]


def test_existing_main_workflow_now_runs_test_planner(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)

    final_state = run_workflow(
        {
            "repo_path": str(fake_repo),
            "target_url": "http://localhost:8000",
            "user_preferences": {
                "test_types": ["api", "ui"],
                "focus": "JWT authentication todo CRUD API tests",
                "planner_use_llm": False,
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["retrieved_context"]
    assert final_state["test_plan"]
    assert (Path("results") / "runs" / final_state["run_id"] / "test_plan.json").exists()
