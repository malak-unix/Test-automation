from __future__ import annotations

from pathlib import Path

from test_auto.agents import ui_testing_agent
from test_auto.graph.ui_testing_workflow import run_ui_testing_workflow
from test_auto.graph.workflow import build_graph
from test_auto.interface.flask_app import create_app
from test_auto.mcp.mcp_config import get_default_mcp_server_command


def fake_ui_plan() -> dict:
    return {
        "ui_tests": [
            {
                "id": "UI_001",
                "name": "login_page_visible",
                "flow": "login",
                "steps": ["open login page"],
                "expected_result": "login form is visible",
                "evidence_sources": ["templates/login.html"],
            }
        ]
    }


def mocked_ui_result(target_url, test_case, run_id, discovered_ui_flows=None, user_preferences=None):
    return {
        "id": test_case.get("id", "UI_001"),
        "name": test_case.get("name", "login_page_visible"),
        "flow": test_case.get("flow"),
        "status": "passed",
        "target_path": "/login/",
        "target_url": f"{target_url.rstrip('/')}/login/",
        "duration_ms": 5.0,
        "details": "mocked",
        "screenshot": None,
        "assertions": [{"type": "login_form_present", "passed": True}],
        "error_type": None,
        "evidence": {"title": "Login"},
    }


def test_ui_testing_workflow_with_mocked_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ui_testing_agent, "execute_ui_test_case", mocked_ui_result)

    final_state = run_ui_testing_workflow(
        {
            "run_id": "ui_workflow_mocked",
            "target_url": "http://localhost:8000",
            "test_plan": fake_ui_plan(),
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["ui_results"]
    assert Path(final_state["ui_result_path"]).exists()


def test_ui_testing_workflow_missing_test_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    final_state = run_ui_testing_workflow(
        {
            "run_id": "ui_workflow_missing_plan",
            "target_url": "http://localhost:8000",
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["ui_results"]["status"] == "partial"
    assert Path(final_state["ui_result_path"]).exists()


def test_existing_main_workflow_includes_ui_agent_after_api_testing() -> None:
    graph_text = str(build_graph().get_graph().nodes)

    assert "report" in graph_text
    assert "ui_testing" in graph_text


def test_existing_dashboard_still_works_with_mocking(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app(testing=True)
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_existing_mcp_integration_still_works() -> None:
    config = get_default_mcp_server_command()

    assert config["testing"]["transport"] == "stdio"
