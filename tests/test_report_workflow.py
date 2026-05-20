from __future__ import annotations

from pathlib import Path
from typing import Any

from test_auto.agents import api_testing_agent
from test_auto.graph.report_workflow import run_report_workflow
from test_auto.graph.workflow import build_graph, run_workflow


def fake_report_state() -> dict[str, Any]:
    return {
        "run_id": "report_workflow_test",
        "target_url": "http://localhost:8000",
        "project_info": {"language": "Python", "framework": "Django REST Framework", "has_api": True},
        "test_plan": {"api_tests": [{"id": "API_001", "endpoint": "/api/todos/"}]},
        "api_results": {
            "summary": {"total_tests": 1, "passed": 1, "failed": 0, "skipped": 0, "errors": 0, "pass_rate": 100.0},
            "tests": [{"id": "API_001", "status": "passed", "method": "GET", "endpoint": "/api/todos/"}],
        },
        "bug_results": {
            "summary": {"total_anomalies": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
            "anomalies": [],
            "recommendations": [],
        },
        "errors": [],
        "agent_logs": [],
    }


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_fake_django_rest_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_report_integration_repo"
    write_file(repo, "README.md", "# Todo API\nJWT authentication protects Todo CRUD API routes.\n")
    write_file(repo, "requirements.txt", "django\ndjangorestframework\ndjangorestframework-simplejwt\npytest\n")
    write_file(repo, "manage.py", "# placeholder\n")
    write_file(
        repo,
        "todo/urls.py",
        "from django.urls import path\nfrom . import views\nurlpatterns = [path(\"api/todos/\", views.todo_list)]\n",
    )
    write_file(
        repo,
        "todo/views.py",
        "def todo_list(request):\n    \"\"\"List todos with JWT auth.\"\"\"\n    pass\n",
    )
    write_file(repo, "templates/login.html", "<form>login</form>\n")
    write_file(repo, "tests/test_todo_api.py", "def test_todo_api(): assert True\n")
    return repo


def mocked_api_result(test_case: dict[str, Any]) -> dict[str, Any]:
    expected = test_case.get("expected_status") or 200
    return {
        "id": str(test_case.get("id") or "API_UNKNOWN"),
        "name": str(test_case.get("name") or "unnamed"),
        "method": str(test_case.get("method") or "GET").upper(),
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


def test_report_workflow_fake_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    final_state = run_report_workflow(fake_report_state())

    assert final_state["final_results"]
    assert final_state["report_html_path"]
    assert final_state["dashboard_payload"]


def test_report_workflow_missing_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    final_state = run_report_workflow({"errors": [], "agent_logs": []})

    assert final_state["final_results"]["status"] == "partial"
    assert Path(final_state["report_html_path"]).exists()


def test_existing_main_workflow_now_reaches_report_agent() -> None:
    graph_text = str(build_graph().get_graph().nodes)

    assert "bug_analysis" in graph_text
    assert "report" in graph_text


def test_existing_bug_integration_still_works_with_mocking(tmp_path: Path, monkeypatch) -> None:
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

    assert final_state["bug_result_path"]
    assert Path(final_state["bug_result_path"]).exists()
    assert final_state["final_results_path"]
    assert Path(final_state["final_results_path"]).exists()
    assert final_state["report_html_path"]
    assert Path(final_state["report_html_path"]).exists()
