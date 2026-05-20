from __future__ import annotations

from pathlib import Path

from test_auto.agents import api_testing_agent
from test_auto.graph.api_testing_workflow import run_api_testing_workflow
from test_auto.graph.workflow import run_workflow


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_fake_django_rest_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_api_workflow_repo"
    write_file(repo, "README.md", "# Todo API\nJWT authentication protects Todo CRUD API routes.\n")
    write_file(repo, "requirements.txt", "django\ndjangorestframework\ndjangorestframework-simplejwt\n")
    write_file(repo, "manage.py", "# placeholder\n")
    write_file(repo, "todo/urls.py", 'path("api/todos/", views.todo_list)\n')
    write_file(repo, "todo/views.py", "def todo_list(request): pass\n")
    write_file(repo, "templates/login.html", "<form>login</form>\n")
    return repo


def sample_test_plan() -> dict:
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
            }
        ]
    }


def mocked_result(test_case: dict) -> dict:
    return {
        "id": test_case["id"],
        "name": test_case["name"],
        "method": test_case["method"],
        "endpoint": test_case["endpoint"],
        "status": "passed",
        "expected_status": 200,
        "actual_status": 200,
        "duration_ms": 10.0,
        "details": "mocked",
        "evidence": {
            "url": "http://localhost:8000/api/todos/",
            "method": "GET",
            "request_body": None,
            "response_preview": "ok",
            "response_json_preview": {"ok": "True"},
        },
        "assertions": [{"type": "status_code", "passed": True}],
        "error_type": None,
    }


def test_api_testing_workflow_with_mocked_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        api_testing_agent,
        "execute_api_test_case",
        lambda target_url, test_case, auth_token=None, timeout_seconds=5: mocked_result(test_case),
    )

    final_state = run_api_testing_workflow(
        {
            "run_id": "api_workflow_test",
            "target_url": "http://localhost:8000",
            "test_plan": sample_test_plan(),
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["api_results"]
    assert final_state["api_result_path"]


def test_api_testing_workflow_missing_test_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    final_state = run_api_testing_workflow(
        {
            "run_id": "api_workflow_empty",
            "target_url": "http://localhost:8000",
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["api_results"]["status"] == "partial"
    assert Path(final_state["api_result_path"]).exists()


def test_existing_main_workflow_now_reaches_api_agent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)
    monkeypatch.setattr(
        api_testing_agent,
        "execute_api_test_case",
        lambda target_url, test_case, auth_token=None, timeout_seconds=5: mocked_result(test_case),
    )

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

    assert final_state["test_plan"]
    assert final_state["api_results"]
    assert (Path("results") / "runs" / final_state["run_id"] / "api_result.json").exists()
