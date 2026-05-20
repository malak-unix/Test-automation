from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_auto.agents import api_testing_agent, ui_testing_agent
from test_auto.agents.bug_analysis_agent import bug_analysis_node
from test_auto.agents.report_agent import report_node
from test_auto.graph.routing import (
    route_after_api_testing,
    route_after_test_planner,
    route_after_ui_testing,
)
from test_auto.graph.ui_testing_workflow import run_ui_testing_workflow
from test_auto.graph.workflow import run_workflow
from test_auto.interface.flask_app import create_app
from test_auto.shared.utils import json_safe


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_fake_django_rest_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_ui_integration_repo"
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
    write_file(repo, "templates/login.html", "<form><input name='username'><input type='password'></form>\n")
    write_file(repo, "tests/test_todo_api.py", "def test_todo_api(): assert True\n")
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
        "name": test_case.get("name", "login_flow_is_visible"),
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


def run_fake_workflow(tmp_path: Path, monkeypatch, preferences: dict[str, Any] | None = None) -> dict[str, Any]:
    monkeypatch.chdir(tmp_path)
    fake_repo = make_fake_django_rest_repo(tmp_path)
    monkeypatch.setattr(api_testing_agent, "execute_api_test_case", mocked_api_result)
    monkeypatch.setattr(ui_testing_agent, "execute_ui_test_case", mocked_ui_result)
    prefs = {
        "test_types": ["api", "ui"],
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


def test_integrated_workflow_runs_ui_testing_fake_repo(tmp_path: Path, monkeypatch) -> None:
    final_state = run_fake_workflow(tmp_path, monkeypatch)

    assert final_state["ui_results"]
    assert final_state["ui_result_path"]
    assert "screenshots" in final_state
    assert final_state["bug_results"]
    assert final_state["final_results"]
    assert final_state["report_html_path"]
    assert Path(final_state["ui_result_path"]).exists()


def test_route_after_test_planner_routes_to_ui_when_api_skipped() -> None:
    state = {
        "selected_agents": ["repository_analyzer", "rag", "test_planner", "ui", "bug", "report"],
        "target_url": "http://localhost:8000",
        "test_plan": {"ui_tests": [{"id": "UI_001", "name": "login", "flow": "login"}]},
        "errors": [],
    }

    assert route_after_test_planner(state) == "ui_testing"


def test_route_after_api_testing_routes_to_ui_when_ui_selected() -> None:
    state = {
        "selected_agents": ["repository_analyzer", "rag", "test_planner", "api", "ui", "bug", "report"],
        "target_url": "http://localhost:8000",
        "test_plan": {"ui_tests": [{"id": "UI_001", "name": "login", "flow": "login"}]},
        "api_results": {"summary": {"total_tests": 1}},
        "errors": [],
    }

    assert route_after_api_testing(state) == "ui_testing"


def test_route_after_ui_testing_routes_to_bug() -> None:
    state = {
        "selected_agents": ["repository_analyzer", "rag", "test_planner", "ui", "bug", "report"],
        "ui_results": {"summary": {"total_tests": 1}},
        "errors": [],
    }

    assert route_after_ui_testing(state) == "bug_analysis"


def test_skip_ui_testing(tmp_path: Path, monkeypatch) -> None:
    final_state = run_fake_workflow(tmp_path, monkeypatch, {"skip_ui_testing": True})

    assert "ui_results" not in final_state or not final_state.get("ui_result_path")
    assert final_state["api_results"]
    assert final_state["bug_results"]
    assert final_state["final_results"]


def test_bug_analysis_includes_ui_anomaly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    patch = bug_analysis_node(
        {
            "run_id": "ui_bug_run",
            "ui_results": {
                "summary": {"total_tests": 1, "passed": 0, "failed": 1, "skipped": 0, "errors": 0, "pass_rate": 0.0},
                "tests": [
                    {
                        "id": "UI_001",
                        "name": "login_page_visible",
                        "flow": "login",
                        "status": "assertion_error",
                        "details": "Expected login form was not visible.",
                        "screenshot": {"path": "results/runs/ui_bug_run/screenshots/UI_001_assertion.png", "created": True},
                        "error_type": "assertion_error",
                    }
                ],
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    anomalies = patch["bug_results"]["anomalies"]
    assert any(item.get("source_agent") == "ui_testing" for item in anomalies)


def test_report_includes_ui_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    patch = report_node(
        {
            "run_id": "ui_report_run",
            "target_url": "http://localhost:8000",
            "project_info": {"language": "Python", "framework": "Django REST Framework", "has_ui": True},
            "test_plan": {"ui_tests": [{"id": "UI_001", "name": "login", "flow": "login"}]},
            "ui_results": {
                "summary": {"total_tests": 1, "passed": 1, "failed": 0, "skipped": 0, "errors": 0, "pass_rate": 100.0},
                "tests": [mocked_ui_result("http://localhost:8000", {"id": "UI_001", "name": "login", "flow": "login"}, "ui_report_run")],
                "screenshots": [],
            },
            "screenshots": [],
            "errors": [],
            "agent_logs": [],
        }
    )

    assert patch["final_results"]["ui_summary"]["total_tests"] == 1
    assert any(section["title"] == "UI Testing" for section in patch["final_results"]["sections"])


def test_dashboard_form_ui_checkbox_enabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = create_app(testing=True).test_client()

    response = client.get("/")
    text = response.get_data(as_text=True)
    ui_input_index = text.index('name="test_types" value="ui"')
    ui_input_fragment = text[ui_input_index : text.index(">", ui_input_index)]

    assert response.status_code == 200
    assert "disabled" not in ui_input_fragment


def test_no_password_token_exposure_in_ui_integration(tmp_path: Path, monkeypatch) -> None:
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


def test_existing_standalone_ui_workflow_still_works(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ui_testing_agent, "execute_ui_test_case", mocked_ui_result)

    final_state = run_ui_testing_workflow(
        {
            "run_id": "standalone_ui_still_works",
            "target_url": "http://localhost:8000",
            "test_plan": {
                "ui_tests": [
                    {
                        "id": "UI_001",
                        "name": "login_page_visible",
                        "flow": "login",
                        "steps": ["open login"],
                        "expected_result": "login form is visible",
                    }
                ]
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["ui_results"]
    assert Path(final_state["ui_result_path"]).exists()
