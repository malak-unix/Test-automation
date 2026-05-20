from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_auto.agents import api_testing_agent
from test_auto.agents.api_testing_agent import run_api_testing_agent_alone
from test_auto.agents.bug_analysis_agent import run_bug_analysis_agent_alone
from test_auto.agents.orchestrator import run_orchestrator_alone
from test_auto.agents.rag_agent import run_rag_agent_alone
from test_auto.agents.report_agent import report_node, run_report_agent_alone
from test_auto.agents.repo_analyzer import run_repo_analyzer_alone
from test_auto.agents.test_planner import run_test_planner_alone
from test_auto.graph.report_workflow import run_report_workflow
from test_auto.graph.routing import route_after_api_testing, route_after_bug_analysis
from test_auto.graph.workflow import run_workflow
from test_auto.shared.utils import json_safe


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
        "def todo_list(request):\n    \"\"\"List, create, update, and delete todos with JWT auth.\"\"\"\n    pass\n",
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
    return [{"method": "GET", "path": "/api/todos/", "source_file": "todo/urls.py"}]


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


def sample_test_plan() -> dict[str, Any]:
    return {
        "scope": "JWT authentication todo CRUD API tests",
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
        ],
        "ui_tests": [],
        "performance_tests": [],
        "missing_information": [],
        "risks": [],
    }


def mocked_api_result(test_case: dict[str, Any]) -> dict[str, Any]:
    method = str(test_case.get("method") or "GET").upper()
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


def run_fake_integrated_workflow(tmp_path: Path, monkeypatch, extra_preferences: dict[str, Any] | None = None) -> dict[str, Any]:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)
    monkeypatch.setattr(
        api_testing_agent,
        "execute_api_test_case",
        lambda target_url, test_case, auth_token=None, timeout_seconds=5: mocked_api_result(test_case),
    )
    preferences = {
        "test_types": ["api"],
        "execution_mode": "sequential",
        "focus": "JWT authentication todo CRUD API tests",
        "rag_top_k": 8,
        "planner_use_llm": False,
        "allow_mutating_api_tests": False,
    }
    preferences.update(extra_preferences or {})
    return run_workflow(
        {
            "repo_path": str(fake_repo),
            "target_url": "http://localhost:8000",
            "user_preferences": preferences,
            "errors": [],
            "agent_logs": [],
        }
    )


def test_integrated_workflow_runs_report_fake_repo(tmp_path: Path, monkeypatch) -> None:
    final_state = run_fake_integrated_workflow(tmp_path, monkeypatch)
    run_dir = Path("results") / "runs" / final_state["run_id"]

    for key in [
        "run_id",
        "selected_agents",
        "project_info",
        "retrieved_context",
        "test_plan",
        "api_results",
        "api_result_path",
        "bug_results",
        "bug_result_path",
        "final_results",
        "final_results_path",
        "report_result_path",
        "report_html_path",
        "dashboard_payload",
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
        "bug_result.json",
        "final_results.json",
        "report_result.json",
        "workflow_state.json",
    ]:
        assert (run_dir / artifact).exists()
    assert Path(final_state["report_html_path"]).exists()


def test_route_after_bug_analysis_valid_state() -> None:
    route = route_after_bug_analysis(
        {
            "selected_agents": ["repository_analyzer", "rag", "test_planner", "api", "bug", "report"],
            "bug_results": {"summary": {"total_anomalies": 1}},
            "api_results": {"summary": {"total_tests": 1}},
            "project_info": {"framework": "Django REST Framework"},
            "errors": [],
        }
    )

    assert route == "report"


def test_route_after_bug_analysis_no_report_selected() -> None:
    route = route_after_bug_analysis(
        {
            "selected_agents": ["repository_analyzer", "rag", "test_planner", "api", "bug"],
            "bug_results": {"summary": {"total_anomalies": 1}},
            "errors": [],
        }
    )

    assert route == "end"


def test_route_after_bug_analysis_skip_report() -> None:
    route = route_after_bug_analysis(
        {
            "selected_agents": ["repository_analyzer", "rag", "test_planner", "api", "bug", "report"],
            "user_preferences": {"skip_report": True},
            "bug_results": {"summary": {"total_anomalies": 1}},
            "errors": [],
        }
    )

    assert route == "end"


def test_route_after_api_testing_routes_to_report_when_bug_skipped() -> None:
    route = route_after_api_testing(
        {
            "selected_agents": ["repository_analyzer", "rag", "test_planner", "api", "report"],
            "api_results": {"summary": {"total_tests": 1}},
            "errors": [],
        }
    )

    assert route == "report"


def test_integrated_report_target_down_still_generates_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)

    final_state = run_workflow(
        {
            "repo_path": str(fake_repo),
            "target_url": "http://127.0.0.1:9",
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

    assert Path(final_state["api_result_path"]).exists()
    assert Path(final_state["bug_result_path"]).exists()
    assert Path(final_state["final_results_path"]).exists()
    assert Path(final_state["report_html_path"]).exists()
    serialized_report = json.dumps(final_state["final_results"])
    assert "environment_error" in serialized_report or "target" in serialized_report.lower()


def test_integrated_report_can_be_skipped(tmp_path: Path, monkeypatch) -> None:
    final_state = run_fake_integrated_workflow(
        tmp_path,
        monkeypatch,
        extra_preferences={"skip_report": True},
    )

    assert Path(final_state["api_result_path"]).exists()
    assert Path(final_state["bug_result_path"]).exists()
    assert "final_results" not in final_state
    assert "report_html_path" not in final_state


def test_report_does_not_expose_auth_token(tmp_path: Path, monkeypatch) -> None:
    token = "SECRET_TOKEN_SHOULD_NOT_APPEAR"
    final_state = run_fake_integrated_workflow(
        tmp_path,
        monkeypatch,
        extra_preferences={"auth_token": token},
    )

    assert token not in json.dumps(json_safe(final_state))
    assert token not in Path(final_state["final_results_path"]).read_text(encoding="utf-8")
    assert token not in Path(final_state["report_result_path"]).read_text(encoding="utf-8")
    assert token not in Path(final_state["report_html_path"]).read_text(encoding="utf-8")


def test_existing_standalone_agents_and_workflows_still_work(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)
    project_info = minimal_project_info()
    indexed_documents = minimal_indexed_documents()
    test_plan = sample_test_plan()
    api_result = run_api_testing_agent_alone(
        target_url="",
        test_plan=test_plan,
        run_id="standalone_report_regression",
        user_preferences={},
        allow_mutating=False,
    )
    bug_result = run_bug_analysis_agent_alone(
        api_results=api_result["api_results"],
        run_id="standalone_report_regression",
    )

    orchestrator = run_orchestrator_alone(
        repo_url="",
        target_url="http://localhost:8000",
        user_preferences={"test_types": ["api"]},
    )
    repo_analyzer = run_repo_analyzer_alone(repo_path=str(fake_repo))
    rag = run_rag_agent_alone(
        repo_path=str(fake_repo),
        project_info=project_info,
        indexed_documents=indexed_documents,
        query="JWT authentication todo CRUD API tests",
    )
    planner = run_test_planner_alone(
        project_info=project_info,
        discovered_endpoints=minimal_endpoints(),
        discovered_ui_flows=[],
        retrieved_context=minimal_retrieved_context(),
        user_preferences={"test_types": ["api"]},
        use_llm=False,
    )
    report = run_report_agent_alone(
        context={
            "run_id": "standalone_report_regression",
            "project_info": project_info,
            "test_plan": test_plan,
            "api_results": api_result["api_results"],
            "bug_results": bug_result["bug_results"],
        }
    )
    workflow = run_report_workflow(
        {
            "run_id": "standalone_report_workflow",
            "project_info": project_info,
            "test_plan": test_plan,
            "api_results": api_result["api_results"],
            "bug_results": bug_result["bug_results"],
            "errors": [],
            "agent_logs": [],
        }
    )

    assert orchestrator["run_id"]
    assert repo_analyzer["project_info"]
    assert rag["retrieved_context"] is not None
    assert planner["test_plan"]
    assert api_result["api_results"]
    assert bug_result["bug_results"]
    assert report["final_results"]
    assert workflow["final_results"]


def test_existing_bug_integration_still_works(tmp_path: Path, monkeypatch) -> None:
    final_state = run_fake_integrated_workflow(tmp_path, monkeypatch)

    assert Path(final_state["bug_result_path"]).exists()
    assert final_state["bug_results"]
