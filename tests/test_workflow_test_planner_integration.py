from __future__ import annotations

import json
from pathlib import Path

from test_auto.agents.orchestrator import run_orchestrator_alone
from test_auto.agents.rag_agent import run_rag_agent_alone
from test_auto.agents.repo_analyzer import run_repo_analyzer_alone
from test_auto.agents.test_planner import run_test_planner_alone
from test_auto.graph.rag_workflow import run_rag_workflow
from test_auto.graph.repo_analyzer_workflow import run_repo_analyzer_workflow
from test_auto.graph.routing import route_after_rag
from test_auto.graph.test_planner_workflow import run_test_planner_workflow
from test_auto.graph.workflow import run_workflow
from test_auto.shared.utils import json_safe


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_fake_django_rest_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_django_rest_planner_repo"
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
    write_file(
        repo,
        "todo/urls.py",
        "from django.urls import path\n"
        "from . import views\n"
        "urlpatterns = [path(\"api/todos/\", views.todo_list)]\n",
    )
    write_file(
        repo,
        "todo/views.py",
        "def todo_list(request):\n"
        "    \"\"\"List, create, update, and delete todo items with JWT auth.\"\"\"\n"
        "    pass\n",
    )
    write_file(repo, "templates/login.html", "<form>JWT login</form>\n")
    write_file(repo, "templates/register.html", "<form>register user</form>\n")
    write_file(repo, "tests/test_todo_api.py", "def test_todo_api(): assert True\n")
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
        "candidate_ui_files": ["templates/login.html", "templates/register.html"],
        "test_dirs": ["tests/test_todo_api.py"],
    }


def minimal_indexed_documents() -> list[dict]:
    return [
        {"path": "README.md", "type": "doc"},
        {"path": "todo/urls.py", "type": "api"},
        {"path": "todo/views.py", "type": "api"},
        {"path": "templates/login.html", "type": "ui"},
        {"path": "templates/register.html", "type": "ui"},
        {"path": "tests/test_todo_api.py", "type": "test"},
    ]


def minimal_endpoints() -> list[dict]:
    return [
        {
            "method": "UNKNOWN",
            "path": "/api/todos/",
            "source_file": "todo/urls.py",
        }
    ]


def minimal_retrieved_context() -> list[dict]:
    return [
        {
            "source_path": "README.md",
            "content": "JWT authentication is required for Todo CRUD API operations.",
            "score": 0.9,
            "reason": "JWT and CRUD evidence",
            "chunk_type": "doc",
        }
    ]


def test_integrated_workflow_runs_repo_rag_planner_fake_repo(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
                "planner_use_llm": False,
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    run_id = final_state["run_id"]
    run_dir = Path("results") / "runs" / run_id
    for key in [
        "selected_agents",
        "orchestrator_decision",
        "project_info",
        "discovered_endpoints",
        "indexed_documents",
        "rag_index_path",
        "rag_query",
        "retrieved_context",
        "test_plan",
        "test_plan_path",
        "test_planner_result_path",
        "planner_model_info",
    ]:
        assert final_state[key]

    assert (run_dir / "orchestrator_result.json").exists()
    assert (run_dir / "repo_analyzer_result.json").exists()
    assert (run_dir / "project_info.json").exists()
    assert (run_dir / "rag_result.json").exists()
    assert (run_dir / "retrieved_context.json").exists()
    assert (run_dir / "rag_index" / "manifest.json").exists()
    assert (run_dir / "test_plan.json").exists()
    assert (run_dir / "test_planner_result.json").exists()
    assert (run_dir / "workflow_state.json").exists()


def test_route_after_rag_valid_state(tmp_path: Path) -> None:
    fake_repo = make_fake_django_rest_repo(tmp_path)

    route = route_after_rag(
        {
            "selected_agents": ["repository_analyzer", "rag", "test_planner"],
            "repo_path": str(fake_repo),
            "project_info": {"language": "Python", "framework": "Django REST Framework"},
            "discovered_endpoints": [{"path": "/api/todos/", "source_file": "todo/urls.py"}],
            "retrieved_context": [
                {"source_path": "README.md", "content": "JWT authentication", "score": 0.9}
            ],
            "errors": [],
        }
    )

    assert route == "test_planner"


def test_route_after_rag_missing_retrieved_context(tmp_path: Path) -> None:
    fake_repo = make_fake_django_rest_repo(tmp_path)

    route = route_after_rag(
        {
            "selected_agents": ["repository_analyzer", "rag", "test_planner"],
            "repo_path": str(fake_repo),
            "project_info": {"language": "Python"},
            "discovered_endpoints": [{"path": "/api/todos/", "source_file": "todo/urls.py"}],
            "errors": [],
        }
    )

    assert route == "end"


def test_route_after_rag_no_test_planner_selected(tmp_path: Path) -> None:
    fake_repo = make_fake_django_rest_repo(tmp_path)

    route = route_after_rag(
        {
            "selected_agents": ["repository_analyzer", "rag"],
            "repo_path": str(fake_repo),
            "project_info": {"language": "Python"},
            "discovered_endpoints": [{"path": "/api/todos/", "source_file": "todo/urls.py"}],
            "retrieved_context": [
                {"source_path": "README.md", "content": "JWT authentication", "score": 0.9}
            ],
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
                "planner_use_llm": False,
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["run_id"]
    assert final_state["errors"]
    assert Path(final_state["workflow_state_path"]).exists()
    assert not (Path("results") / "runs" / final_state["run_id"] / "test_plan.json").exists()


def test_integrated_planner_does_not_call_llm_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "placeholder_groq")
    monkeypatch.setenv("MISTRAL_API_KEY", "placeholder_mistral")
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
    state_text = json.dumps(json_safe(final_state))

    assert final_state["planner_model_info"]["mode"] == "deterministic_fallback"
    assert "placeholder_groq" not in json.dumps(final_state["planner_model_info"])
    assert "placeholder_mistral" not in json.dumps(final_state["planner_model_info"])
    assert "placeholder_groq" not in state_text
    assert "placeholder_mistral" not in state_text


def test_test_plan_in_final_state_has_evidence_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
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

    for item in final_state["test_plan"]["api_tests"]:
        assert item["id"]
        assert item["name"]
        assert item["endpoint"]
        assert item["evidence_sources"]
    for item in final_state["test_plan"]["ui_tests"]:
        assert item["id"]
        assert item["name"]
        assert item.get("flow") or item.get("steps")
        assert item["evidence_sources"]


def test_existing_standalone_agents_still_work(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)

    orchestrator_result = run_orchestrator_alone(
        repo_url="https://github.com/Vitaee/DjangoRestAPI",
        target_url="http://localhost:8000",
        user_preferences={"test_types": ["api", "ui"], "execution_mode": "sequential"},
    )
    analyzer_result = run_repo_analyzer_alone(repo_path=str(fake_repo))
    rag_result = run_rag_agent_alone(
        repo_path=str(fake_repo),
        project_info=minimal_project_info(),
        indexed_documents=minimal_indexed_documents(),
        query="JWT authentication todo CRUD API tests",
    )
    planner_result = run_test_planner_alone(
        project_info=minimal_project_info(),
        discovered_endpoints=minimal_endpoints(),
        retrieved_context=minimal_retrieved_context(),
        use_llm=False,
    )

    assert orchestrator_result["orchestrator_decision"]
    assert analyzer_result["project_info"]
    assert rag_result["retrieved_context"]
    assert planner_result["test_plan"]


def test_existing_mini_workflows_still_work(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)

    repo_state = run_repo_analyzer_workflow(
        {"repo_path": str(fake_repo), "errors": [], "agent_logs": []}
    )
    rag_state = run_rag_workflow(
        {
            "repo_path": str(fake_repo),
            "project_info": minimal_project_info(),
            "indexed_documents": minimal_indexed_documents(),
            "rag_query": "JWT authentication todo CRUD API tests",
            "errors": [],
            "agent_logs": [],
        }
    )
    planner_state = run_test_planner_workflow(
        {
            "project_info": minimal_project_info(),
            "discovered_endpoints": minimal_endpoints(),
            "retrieved_context": minimal_retrieved_context(),
            "user_preferences": {"planner_use_llm": False},
            "errors": [],
            "agent_logs": [],
        }
    )

    assert repo_state["project_info"]
    assert rag_state["retrieved_context"]
    assert planner_state["test_plan"]
