from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_auto.agents import api_testing_agent, performance_testing_agent, ui_testing_agent
from test_auto.agents.bug_analysis_agent import bug_analysis_node
from test_auto.agents.report_agent import report_node
from test_auto.graph.performance_testing_workflow import run_performance_testing_workflow
from test_auto.graph.routing import (
    route_after_api_testing,
    route_after_performance_testing,
    route_after_ui_testing,
)
from test_auto.graph.workflow import run_workflow
from test_auto.interface.flask_app import create_app
from test_auto.interface.run_service import build_initial_state_from_form
from test_auto.shared.utils import json_safe


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_fake_django_rest_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_performance_integration_repo"
    write_file(repo, "README.md", "# Todo API\nJWT authentication protects Todo CRUD API routes.\n")
    write_file(repo, "requirements.txt", "django\ndjangorestframework\npytest\n")
    write_file(repo, "manage.py", "# placeholder\n")
    write_file(
        repo,
        "todo/urls.py",
        "from django.urls import path\nfrom . import views\nurlpatterns = [path(\"api/todos/\", views.todo_list)]\n",
    )
    write_file(repo, "todo/views.py", "def todo_list(request): pass\n")
    write_file(repo, "templates/login.html", "<form><input name='username'><input type='password'></form>\n")
    return repo


def mocked_api_result(target_url: str, test_case: dict[str, Any], **kwargs) -> dict[str, Any]:
    expected = test_case.get("expected_status") or 200
    return {
        "id": test_case.get("id", "API_001"),
        "name": test_case.get("name", "api_smoke"),
        "method": test_case.get("method", "GET"),
        "endpoint": test_case.get("endpoint", "/api/todos/"),
        "status": "passed",
        "expected_status": expected,
        "actual_status": expected,
        "duration_ms": 7.0,
        "details": "mocked API execution",
        "evidence": {},
        "assertions": [{"type": "status_code", "passed": True}],
        "error_type": None,
    }


def mocked_ui_result(
    target_url: str,
    test_case: dict[str, Any],
    run_id: str,
    discovered_ui_flows: list[dict[str, Any]] | None = None,
    user_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": test_case.get("id", "UI_001"),
        "name": test_case.get("name", "login_page_visible"),
        "flow": test_case.get("flow", "login"),
        "status": "passed",
        "target_path": "/login/",
        "target_url": f"{target_url.rstrip('/')}/login/",
        "duration_ms": 6.0,
        "details": "mocked UI execution",
        "screenshot": None,
        "assertions": [{"type": "login_form_present", "passed": True}],
        "error_type": None,
        "evidence": {"title": "Login"},
    }


def mocked_performance_result(
    target_url: str,
    test_case: dict[str, Any],
    run_id: str,
    user_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = f"results/runs/{run_id}/performance/locustfile_PERF_001.py"
    return {
        "id": test_case.get("id", "PERF_001"),
        "name": test_case.get("name", "todo_list_perf"),
        "endpoint": test_case.get("endpoint", "/api/todos/"),
        "method": "GET",
        "status": "passed",
        "users": 1,
        "spawn_rate": 1.0,
        "duration_seconds": 1,
        "total_requests": 12,
        "failures": 0,
        "failure_rate": 0.0,
        "average_response_time_ms": 30.0,
        "min_response_time_ms": 10.0,
        "max_response_time_ms": 80.0,
        "p50_response_time_ms": 25.0,
        "p95_response_time_ms": 70.0,
        "requests_per_second": 6.0,
        "threshold_results": [{"name": "average_response_time", "passed": True}],
        "details": "mocked performance execution",
        "error_type": None,
        "artifact_paths": [artifact],
    }


def run_fake_workflow(
    tmp_path: Path,
    monkeypatch,
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)
    monkeypatch.setattr(api_testing_agent, "execute_api_test_case", mocked_api_result)
    monkeypatch.setattr(ui_testing_agent, "execute_ui_test_case", mocked_ui_result)
    monkeypatch.setattr(
        performance_testing_agent,
        "execute_performance_test_case",
        mocked_performance_result,
    )
    prefs = {
        "test_types": ["api", "ui", "performance"],
        "execution_mode": "sequential",
        "focus": "JWT authentication todo CRUD API tests",
        "rag_top_k": 8,
        "planner_use_llm": False,
        "allow_mutating_api_tests": False,
    }
    prefs.update(preferences or {})
    return run_workflow(
        {
            "repo_path": str(fake_repo),
            "target_url": "http://localhost:8000",
            "user_preferences": prefs,
            "errors": [],
            "agent_logs": [],
        }
    )


def test_integrated_workflow_runs_performance_testing_fake_repo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    final_state = run_fake_workflow(tmp_path, monkeypatch)

    assert final_state["performance_results"]
    assert final_state["performance_result_path"]
    assert final_state["performance_artifacts"]
    assert final_state["bug_results"]
    assert final_state["final_results"]
    assert final_state["report_html_path"]
    assert Path(final_state["performance_result_path"]).exists()


def test_route_after_ui_testing_routes_to_performance() -> None:
    state = {
        "selected_agents": ["performance", "bug", "report"],
        "target_url": "http://localhost:8000",
        "test_plan": {"performance_tests": [{"id": "PERF_001", "endpoint": "/", "method": "GET"}]},
        "ui_results": {"summary": {"total_tests": 1}},
        "errors": [],
    }

    assert route_after_ui_testing(state) == "performance_testing"


def test_route_after_api_testing_routes_to_performance_when_ui_skipped() -> None:
    state = {
        "selected_agents": ["api", "performance", "bug", "report"],
        "target_url": "http://localhost:8000",
        "test_plan": {"api_tests": [{"id": "API_001", "endpoint": "/api/todos/", "method": "GET"}]},
        "api_results": {"summary": {"total_tests": 1}},
        "errors": [],
    }

    assert route_after_api_testing(state) == "performance_testing"


def test_route_after_performance_testing_routes_to_bug() -> None:
    state = {
        "selected_agents": ["performance", "bug", "report"],
        "performance_results": {"summary": {"total_tests": 1}},
        "errors": [],
    }

    assert route_after_performance_testing(state) == "bug_analysis"


def test_skip_performance_testing(tmp_path: Path, monkeypatch) -> None:
    final_state = run_fake_workflow(
        tmp_path,
        monkeypatch,
        {"skip_performance_testing": True},
    )

    assert "performance_results" not in final_state or not final_state.get("performance_result_path")
    assert final_state["api_results"]
    assert final_state["ui_results"]
    assert final_state["bug_results"]
    assert final_state["final_results"]


def test_bug_analysis_includes_performance_anomaly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    patch = bug_analysis_node(
        {
            "run_id": "perf_bug_run",
            "performance_results": {
                "summary": {
                    "total_tests": 1,
                    "passed": 0,
                    "failed": 1,
                    "skipped": 0,
                    "errors": 0,
                    "overall_failure_rate": 0.0,
                },
                "tests": [
                    {
                        **mocked_performance_result(
                            "http://localhost:8000",
                            {"id": "PERF_001", "endpoint": "/api/todos/"},
                            "perf_bug_run",
                        ),
                        "status": "performance_threshold_failed",
                        "error_type": "performance_threshold_failed",
                        "threshold_results": [
                            {
                                "name": "p95_response_time",
                                "passed": False,
                                "actual": 7000,
                                "threshold": 5000,
                            }
                        ],
                    }
                ],
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    anomalies = patch["bug_results"]["anomalies"]
    assert any(item.get("source_agent") == "performance_testing" for item in anomalies)


def test_report_includes_performance_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    perf_result = mocked_performance_result(
        "http://localhost:8000",
        {"id": "PERF_001", "endpoint": "/api/todos/"},
        "perf_report_run",
    )
    patch = report_node(
        {
            "run_id": "perf_report_run",
            "target_url": "http://localhost:8000",
            "project_info": {"language": "Python", "framework": "Django REST Framework", "has_api": True},
            "test_plan": {"performance_tests": [{"id": "PERF_001", "endpoint": "/api/todos/"}]},
            "performance_results": {
                "summary": {
                    "total_tests": 1,
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                    "errors": 0,
                    "average_response_time_ms": 30.0,
                    "p95_response_time_ms": 70.0,
                    "overall_failure_rate": 0.0,
                },
                "tests": [perf_result],
                "artifacts": [],
            },
            "performance_artifacts": [],
            "errors": [],
            "agent_logs": [],
        }
    )

    assert patch["final_results"]["performance_summary"]["total_tests"] == 1
    assert any(section["title"] == "Performance Testing" for section in patch["final_results"]["sections"])


def test_dashboard_form_performance_checkbox_exists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = create_app(testing=True).test_client()

    response = client.get("/")
    text = response.get_data(as_text=True)
    perf_input_index = text.index('name="test_types" value="performance"')
    perf_input_fragment = text[perf_input_index : text.index(">", perf_input_index)]

    assert response.status_code == 200
    assert "disabled" not in perf_input_fragment
    assert "allow_external_performance_test" in text


def test_dashboard_form_parses_performance_options() -> None:
    state = build_initial_state_from_form(
        {
            "repo_url": "https://github.com/Vitaee/DjangoRestAPI",
            "target_url": "http://localhost:8000",
            "test_types": ["api", "performance"],
            "allow_external_performance_test": "on",
            "skip_performance_testing": "on",
        }
    )

    assert "performance" in state["user_preferences"]["test_types"]
    assert state["user_preferences"]["allow_external_performance_test"] is True
    assert state["user_preferences"]["skip_performance_testing"] is True


def test_no_secret_exposure_in_performance_integration(tmp_path: Path, monkeypatch) -> None:
    password = "RAW_PASSWORD_SHOULD_NOT_APPEAR"
    token = "RAW_TOKEN_SHOULD_NOT_APPEAR"
    final_state = run_fake_workflow(
        tmp_path,
        monkeypatch,
        {"password": password, "token": token},
    )

    serialized_state = json.dumps(json_safe(final_state))
    final_results_text = Path(final_state["final_results_path"]).read_text(encoding="utf-8")
    report_result_text = Path(final_state["report_result_path"]).read_text(encoding="utf-8")
    html_text = Path(final_state["report_html_path"]).read_text(encoding="utf-8")

    for secret in (password, token):
        assert secret not in serialized_state
        assert secret not in final_results_text
        assert secret not in report_result_text
        assert secret not in html_text


def test_existing_standalone_performance_workflow_still_works(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        performance_testing_agent,
        "execute_performance_test_case",
        mocked_performance_result,
    )

    final_state = run_performance_testing_workflow(
        {
            "run_id": "standalone_perf_still_works",
            "target_url": "http://localhost:8000",
            "test_plan": {
                "performance_tests": [
                    {
                        "id": "PERF_001",
                        "name": "todo_list_perf",
                        "endpoint": "/api/todos/",
                        "method": "GET",
                    }
                ]
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["performance_results"]
    assert Path(final_state["performance_result_path"]).exists()
