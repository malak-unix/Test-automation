from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_auto.agents import api_testing_agent
from test_auto.agents.api_testing_agent import (
    api_testing_node,
    run_api_testing_agent_alone,
)
from test_auto.agents.orchestrator import run_orchestrator_alone
from test_auto.agents.rag_agent import run_rag_agent_alone
from test_auto.agents.repo_analyzer import run_repo_analyzer_alone
from test_auto.agents.test_planner import run_test_planner_alone
from test_auto.graph.api_testing_workflow import run_api_testing_workflow
from test_auto.graph.routing import route_after_test_planner
from test_auto.graph.workflow import run_workflow
from test_auto.shared.utils import json_safe


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_fake_django_rest_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_api_integration_repo"
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
    write_file(repo, "templates/login.html", "<form>login</form>\n")
    write_file(repo, "tests/test_todo_api.py", "def test_todo_api(): assert True\n")
    return repo


def minimal_project_info() -> dict[str, Any]:
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


def minimal_indexed_documents() -> list[dict[str, Any]]:
    return [
        {"path": "README.md", "type": "doc"},
        {"path": "todo/urls.py", "type": "api"},
        {"path": "todo/views.py", "type": "api"},
        {"path": "templates/login.html", "type": "ui"},
        {"path": "tests/test_todo_api.py", "type": "test"},
    ]


def minimal_endpoints() -> list[dict[str, Any]]:
    return [
        {
            "method": "UNKNOWN",
            "path": "/api/todos/",
            "source_file": "todo/urls.py",
        }
    ]


def minimal_retrieved_context() -> list[dict[str, Any]]:
    return [
        {
            "source_path": "README.md",
            "content": "JWT authentication is required for Todo CRUD API operations.",
            "score": 0.9,
            "reason": "JWT and CRUD evidence",
            "chunk_type": "doc",
        }
    ]


def sample_get_post_plan() -> dict[str, Any]:
    return {
        "api_tests": [
            {
                "id": "API_001",
                "name": "list_todos",
                "method": "GET",
                "endpoint": "/api/todos/",
                "expected_status": 200,
                "assertions": [{"type": "status_code", "expected": "200"}],
                "evidence_sources": ["todo/urls.py"],
            },
            {
                "id": "API_002",
                "name": "create_todo",
                "method": "POST",
                "endpoint": "/api/todos/",
                "expected_status": 201,
                "request_body": {"title": "demo"},
                "assertions": [{"type": "status_code", "expected": "201"}],
                "evidence_sources": ["todo/urls.py"],
            },
        ]
    }


def mocked_api_result(test_case: dict[str, Any]) -> dict[str, Any]:
    method = str(test_case.get("method") or "UNKNOWN").upper()
    expected = test_case.get("expected_status") or 200
    return {
        "id": str(test_case.get("id") or "API_UNKNOWN"),
        "name": str(test_case.get("name") or "unnamed"),
        "method": method,
        "endpoint": str(test_case.get("endpoint") or ""),
        "status": "passed",
        "expected_status": expected,
        "actual_status": expected,
        "duration_ms": 8.0,
        "details": "mocked integrated API execution",
        "evidence": {
            "url": "http://localhost:8000/api/todos/",
            "method": method,
            "request_body": None,
            "response_preview": "{\"ok\": true}",
            "response_json_preview": {"ok": "True"},
        },
        "assertions": [{"type": "status_code", "passed": True}],
        "error_type": None,
    }


def test_integrated_workflow_runs_api_testing_fake_repo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)
    monkeypatch.setattr(
        api_testing_agent,
        "execute_api_test_case",
        lambda target_url, test_case, auth_token=None, timeout_seconds=5: mocked_api_result(test_case),
    )

    final_state = run_workflow(
        {
            "repo_path": str(fake_repo),
            "target_url": "http://localhost:8000",
            "user_preferences": {
                "test_types": ["api"],
                "execution_mode": "sequential",
                "focus": "JWT authentication todo CRUD API tests",
                "rag_top_k": 8,
                "planner_use_llm": False,
                "allow_mutating_api_tests": False,
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    run_dir = Path("results") / "runs" / final_state["run_id"]
    for key in [
        "run_id",
        "selected_agents",
        "project_info",
        "retrieved_context",
        "test_plan",
        "api_results",
        "api_result_path",
    ]:
        assert final_state[key]

    for artifact in [
        "orchestrator_result.json",
        "repo_analyzer_result.json",
        "project_info.json",
        "rag_result.json",
        "retrieved_context.json",
        "test_plan.json",
        "test_planner_result.json",
        "api_result.json",
        "workflow_state.json",
    ]:
        assert (run_dir / artifact).exists()


def test_route_after_test_planner_valid_state() -> None:
    route = route_after_test_planner(
        {
            "selected_agents": ["repository_analyzer", "rag", "test_planner", "api"],
            "target_url": "http://localhost:8000",
            "test_plan": {
                "api_tests": [
                    {
                        "id": "API_001",
                        "name": "list_todos",
                        "method": "GET",
                        "endpoint": "/api/todos/",
                    }
                ]
            },
            "errors": [],
        }
    )

    assert route == "api_testing"


def test_route_after_test_planner_no_api_selected() -> None:
    route = route_after_test_planner(
        {
            "selected_agents": ["repository_analyzer", "rag", "test_planner"],
            "target_url": "http://localhost:8000",
            "test_plan": {"api_tests": [{"id": "API_001", "endpoint": "/api/todos/"}]},
            "errors": [],
        }
    )

    assert route == "end"


def test_route_after_test_planner_missing_test_plan() -> None:
    route = route_after_test_planner(
        {
            "selected_agents": ["repository_analyzer", "rag", "test_planner", "api"],
            "target_url": "http://localhost:8000",
            "errors": [],
        }
    )

    assert route == "end"


def test_integrated_workflow_target_down_records_environment_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)

    final_state = run_workflow(
        {
            "repo_path": str(fake_repo),
            "target_url": "http://127.0.0.1:9",
            "user_preferences": {
                "test_types": ["api"],
                "focus": "JWT authentication todo CRUD API tests",
                "planner_use_llm": False,
                "allow_mutating_api_tests": False,
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    api_tests = final_state["api_results"]["tests"]
    assert Path(final_state["api_result_path"]).exists()
    assert any(item["status"] == "environment_error" for item in api_tests)


def test_integrated_api_skips_mutating_methods_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        api_testing_agent,
        "execute_api_test_case",
        lambda target_url, test_case, auth_token=None, timeout_seconds=5: mocked_api_result(test_case),
    )

    update = api_testing_node(
        {
            "run_id": "safe_mode_run",
            "target_url": "http://localhost:8000",
            "test_plan": sample_get_post_plan(),
            "user_preferences": {"allow_mutating_api_tests": False},
            "errors": [],
            "agent_logs": [],
        }
    )

    post_result = next(item for item in update["api_results"]["tests"] if item["method"] == "POST")
    assert post_result["status"] == "skipped"
    assert "mutating API tests are disabled" in post_result["details"]


def test_integrated_api_allows_mutating_methods_when_flag_true(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        api_testing_agent,
        "execute_api_test_case",
        lambda target_url, test_case, auth_token=None, timeout_seconds=5: mocked_api_result(test_case),
    )

    update = api_testing_node(
        {
            "run_id": "mutating_allowed_run",
            "target_url": "http://localhost:8000",
            "test_plan": sample_get_post_plan(),
            "user_preferences": {"allow_mutating_api_tests": True},
            "errors": [],
            "agent_logs": [],
        }
    )

    post_result = next(item for item in update["api_results"]["tests"] if item["method"] == "POST")
    assert post_result["status"] == "passed"
    assert "mutating API tests are disabled" not in post_result["details"]


def test_api_result_does_not_expose_auth_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    token = "SECRET_TOKEN_SHOULD_NOT_APPEAR"
    monkeypatch.setattr(
        api_testing_agent,
        "execute_api_test_case",
        lambda target_url, test_case, auth_token=None, timeout_seconds=5: mocked_api_result(test_case),
    )

    update = api_testing_node(
        {
            "run_id": "token_run",
            "target_url": "http://localhost:8000",
            "test_plan": sample_get_post_plan(),
            "user_preferences": {
                "auth_token": token,
                "allow_mutating_api_tests": False,
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    assert token not in json.dumps(json_safe(update))
    assert update["user_preferences"]["auth_token"] == "***MASKED***"


def test_existing_standalone_agents_and_workflows_still_work(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)
    monkeypatch.setattr(
        api_testing_agent,
        "execute_api_test_case",
        lambda target_url, test_case, auth_token=None, timeout_seconds=5: mocked_api_result(test_case),
    )

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
    planner_result = run_test_planner_alone(
        project_info=minimal_project_info(),
        discovered_endpoints=minimal_endpoints(),
        retrieved_context=minimal_retrieved_context(),
        use_llm=False,
    )
    api_result = run_api_testing_agent_alone(
        target_url="http://localhost:8000",
        test_plan=sample_get_post_plan(),
    )
    api_workflow_state = run_api_testing_workflow(
        {
            "run_id": "api_mini_still_works",
            "target_url": "http://localhost:8000",
            "test_plan": sample_get_post_plan(),
            "errors": [],
            "agent_logs": [],
        }
    )

    assert orchestrator_result["orchestrator_decision"]
    assert analyzer_result["project_info"]
    assert rag_result["retrieved_context"]
    assert planner_result["test_plan"]
    assert api_result["api_results"]
    assert api_workflow_state["api_results"]
