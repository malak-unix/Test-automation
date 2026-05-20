from __future__ import annotations

from pathlib import Path
from typing import Any

from test_auto.agents import api_testing_agent
from test_auto.graph.bug_analysis_workflow import run_bug_analysis_workflow
from test_auto.graph.workflow import run_workflow


def fake_api_results() -> dict[str, Any]:
    return {
        "summary": {
            "total_tests": 2,
            "passed": 1,
            "failed": 0,
            "skipped": 0,
            "errors": 1,
            "pass_rate": 50.0,
        },
        "tests": [
            {
                "id": "API_001",
                "name": "list_todos",
                "method": "GET",
                "endpoint": "/api/todos/",
                "status": "passed",
                "expected_status": 200,
                "actual_status": 200,
            },
            {
                "id": "API_002",
                "name": "target_down",
                "method": "GET",
                "endpoint": "/api/todos/",
                "status": "environment_error",
                "expected_status": 200,
                "actual_status": None,
                "details": "Connection refused",
            },
        ],
    }


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_fake_django_rest_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_bug_workflow_repo"
    write_file(repo, "README.md", "# Todo API\nJWT authentication protects Todo CRUD API routes.\n")
    write_file(repo, "requirements.txt", "django\ndjangorestframework\ndjangorestframework-simplejwt\n")
    write_file(repo, "manage.py", "# placeholder\n")
    write_file(
        repo,
        "todo/urls.py",
        "from django.urls import path\nfrom . import views\nurlpatterns = [path(\"api/todos/\", views.todo_list)]\n",
    )
    write_file(
        repo,
        "todo/views.py",
        "def todo_list(request):\n    \"\"\"List, create, update, and delete todos with JWT auth.\"\"\"\n    pass\n",
    )
    write_file(repo, "templates/login.html", "<form>login</form>\n")
    write_file(repo, "tests/test_todo_api.py", "def test_todo_api(): assert True\n")
    return repo


def mocked_api_result(test_case: dict[str, Any]) -> dict[str, Any]:
    method = str(test_case.get("method") or "UNKNOWN").upper()
    if method == "UNKNOWN":
        return {
            "id": str(test_case.get("id") or "API_UNKNOWN"),
            "name": str(test_case.get("name") or "unnamed"),
            "method": method,
            "endpoint": str(test_case.get("endpoint") or ""),
            "status": "skipped",
            "expected_status": test_case.get("expected_status"),
            "actual_status": None,
            "duration_ms": None,
            "details": "HTTP method is UNKNOWN and cannot be safely executed.",
            "evidence": {},
            "assertions": [],
            "error_type": None,
        }
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
        "details": "mocked",
        "evidence": {},
        "assertions": [{"type": "status_code", "passed": True}],
        "error_type": None,
    }


def test_bug_analysis_workflow_fake_api_results(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    final_state = run_bug_analysis_workflow(
        {
            "run_id": "bug_workflow_test",
            "api_results": fake_api_results(),
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["bug_results"]
    assert final_state["bug_result_path"]
    assert final_state["recommendations"]


def test_bug_analysis_workflow_missing_api_results(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    final_state = run_bug_analysis_workflow(
        {
            "run_id": "bug_workflow_missing",
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["bug_results"]["status"] == "partial"
    assert final_state["bug_results"]["summary"]["info"] >= 1


def test_existing_main_workflow_now_reaches_bug_agent(
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
                "focus": "JWT authentication todo CRUD API tests",
                "planner_use_llm": False,
                "allow_mutating_api_tests": False,
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["api_results"]
    assert final_state["bug_results"]
    assert Path(final_state["bug_result_path"]).exists()


def test_existing_api_integration_still_works_with_mocking(
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
                "focus": "JWT authentication todo CRUD API tests",
                "planner_use_llm": False,
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["api_result_path"]
    assert Path(final_state["api_result_path"]).exists()
