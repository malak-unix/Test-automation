from __future__ import annotations

from pathlib import Path

from test_auto.agents.orchestrator import run_orchestrator_alone
from test_auto.agents.rag_agent import run_rag_agent_alone
from test_auto.agents.repo_analyzer import run_repo_analyzer_alone
from test_auto.graph.routing import route_after_repo_analyzer
from test_auto.graph.workflow import run_workflow


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_fake_django_rest_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_django_rest_repo"
    write_file(
        repo,
        "README.md",
        "# Todo API\nJWT authentication protects Todo CRUD API routes.\n",
    )
    write_file(
        repo,
        "requirements.txt",
        "django\ndjangorestframework\ndjangorestframework-simplejwt\npytest\n",
    )
    write_file(repo, "manage.py", "# placeholder\n")
    write_file(repo, "todo/urls.py", 'path("api/todos/", views.todo_list)\n')
    write_file(
        repo,
        "todo/views.py",
        "def list_todos(request): pass\n"
        "def create_todo(request): pass\n"
        "def update_todo(request): pass\n"
        "def delete_todo(request): pass\n",
    )
    write_file(repo, "templates/login.html", "<form>JWT login</form>\n")
    write_file(repo, "tests/test_todo_api.py", "def test_todo_list(): assert True\n")
    return repo


def minimal_project_info() -> dict:
    return {
        "language": "Python",
        "framework": "Django REST Framework",
        "has_api": True,
        "has_ui": True,
        "auth_type": "JWT",
        "candidate_docs": ["README.md"],
        "candidate_api_files": ["todo/urls.py", "todo/views.py"],
        "candidate_ui_files": ["templates/login.html"],
        "test_dirs": ["tests/test_todo_api.py"],
    }


def minimal_indexed_documents() -> list[dict]:
    return [
        {"path": "README.md", "type": "doc"},
        {"path": "todo/urls.py", "type": "api"},
        {"path": "todo/views.py", "type": "api"},
        {"path": "templates/login.html", "type": "ui"},
        {"path": "tests/test_todo_api.py", "type": "test"},
    ]


def test_integrated_workflow_runs_repo_and_rag_fake_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)

    final_state = run_workflow(
        {
            "repo_path": str(fake_repo),
            "target_url": "http://localhost:8000",
            "user_preferences": {
                "test_types": ["api", "ui"],
                "execution_mode": "sequential",
                "focus": "JWT authentication todo CRUD API tests",
                "rag_top_k": 8,
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    run_id = final_state["run_id"]
    run_dir = Path("results") / "runs" / run_id
    assert final_state["selected_agents"]
    assert final_state["orchestrator_decision"]
    assert final_state["project_info"]
    assert final_state["discovered_endpoints"]
    assert final_state["indexed_documents"]
    assert final_state["rag_index_path"]
    assert final_state["rag_query"]
    assert final_state["retrieved_context"]
    assert "missing_information" in final_state
    assert (run_dir / "orchestrator_result.json").exists()
    assert (run_dir / "repo_analyzer_result.json").exists()
    assert (run_dir / "project_info.json").exists()
    assert (run_dir / "rag_result.json").exists()
    assert (run_dir / "retrieved_context.json").exists()
    assert (run_dir / "rag_index" / "manifest.json").exists()
    assert (run_dir / "workflow_state.json").exists()


def test_route_after_repo_analyzer_valid_state(tmp_path: Path) -> None:
    fake_repo = make_fake_django_rest_repo(tmp_path)

    route = route_after_repo_analyzer(
        {
            "selected_agents": ["repository_analyzer", "rag", "test_planner"],
            "repo_path": str(fake_repo),
            "project_info": {"language": "Python", "framework": "Django REST Framework"},
            "indexed_documents": [{"path": "README.md", "type": "doc"}],
            "errors": [],
        }
    )

    assert route == "rag"


def test_route_after_repo_analyzer_missing_project_info(tmp_path: Path) -> None:
    fake_repo = make_fake_django_rest_repo(tmp_path)

    route = route_after_repo_analyzer(
        {
            "selected_agents": ["repository_analyzer", "rag"],
            "repo_path": str(fake_repo),
            "indexed_documents": [{"path": "README.md", "type": "doc"}],
            "errors": [],
        }
    )

    assert route == "end"


def test_route_after_repo_analyzer_no_rag_selected(tmp_path: Path) -> None:
    fake_repo = make_fake_django_rest_repo(tmp_path)

    route = route_after_repo_analyzer(
        {
            "selected_agents": ["repository_analyzer"],
            "repo_path": str(fake_repo),
            "project_info": {"language": "Python"},
            "indexed_documents": [{"path": "README.md", "type": "doc"}],
            "errors": [],
        }
    )

    assert route == "end"


def test_integrated_workflow_invalid_repo_does_not_crash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    final_state = run_workflow(
        {
            "repo_url": "not-a-url",
            "target_url": "http://localhost:8000",
            "user_preferences": {
                "test_types": ["api"],
                "focus": "JWT authentication todo CRUD API tests",
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["run_id"]
    assert final_state["errors"]
    assert Path(final_state["workflow_state_path"]).exists()
    assert not (Path("results") / "runs" / final_state["run_id"] / "rag_result.json").exists()


def test_existing_standalone_agents_still_work(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)

    orchestrator_result = run_orchestrator_alone(
        repo_url="https://github.com/Vitaee/DjangoRestAPI",
        target_url="http://localhost:8000",
        user_preferences={"test_types": ["api"], "execution_mode": "sequential"},
    )
    analyzer_result = run_repo_analyzer_alone(repo_path=str(fake_repo))
    rag_result = run_rag_agent_alone(
        repo_path=str(fake_repo),
        project_info=minimal_project_info(),
        indexed_documents=minimal_indexed_documents(),
        query="JWT authentication todo CRUD API tests",
    )

    assert orchestrator_result["orchestrator_decision"]
    assert analyzer_result["project_info"]
    assert rag_result["retrieved_context"]


def test_rag_retrieval_in_final_state_has_sources(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)

    final_state = run_workflow(
        {
            "repo_path": str(fake_repo),
            "target_url": "http://localhost:8000",
            "user_preferences": {
                "test_types": ["api", "ui"],
                "focus": "JWT authentication todo CRUD API tests",
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    for item in final_state["retrieved_context"]:
        assert item["source_path"]
        assert item["content"]
        assert isinstance(item["score"], float)
        assert item["reason"]
