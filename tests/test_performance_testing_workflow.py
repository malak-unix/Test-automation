from __future__ import annotations

from pathlib import Path

from test_auto.agents import performance_testing_agent
from test_auto.graph.performance_testing_workflow import run_performance_testing_workflow
from test_auto.graph.workflow import build_graph
from test_auto.interface.flask_app import create_app
from test_auto.mcp.mcp_config import get_default_mcp_server_command


def fake_performance_plan() -> dict:
    return {
        "performance_tests": [
            {
                "id": "PERF_001",
                "name": "todo_list_perf",
                "endpoint": "/api/todos/",
                "method": "GET",
            }
        ]
    }


def mocked_performance_result(target_url, test_case, run_id, user_preferences=None):
    return {
        "id": test_case.get("id", "PERF_001"),
        "name": test_case.get("name", "todo_list_perf"),
        "endpoint": test_case.get("endpoint", "/api/todos/"),
        "method": "GET",
        "status": "passed",
        "users": 1,
        "spawn_rate": 1.0,
        "duration_seconds": 1,
        "total_requests": 10,
        "failures": 0,
        "failure_rate": 0.0,
        "average_response_time_ms": 25.0,
        "min_response_time_ms": 10.0,
        "max_response_time_ms": 50.0,
        "p50_response_time_ms": 20.0,
        "p95_response_time_ms": 45.0,
        "requests_per_second": 5.0,
        "threshold_results": [{"name": "average_response_time", "passed": True}],
        "details": "mocked",
        "error_type": None,
        "artifact_paths": [f"results/runs/{run_id}/performance/locustfile_PERF_001.py"],
    }


def test_performance_testing_workflow_with_mocked_execution(
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
            "run_id": "perf_workflow_mocked",
            "target_url": "http://localhost:8000",
            "test_plan": fake_performance_plan(),
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["performance_results"]
    assert Path(final_state["performance_result_path"]).exists()


def test_performance_testing_workflow_missing_test_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    final_state = run_performance_testing_workflow(
        {
            "run_id": "perf_workflow_missing_plan",
            "target_url": "https://example.com",
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["performance_results"]["status"] == "partial"
    assert Path(final_state["performance_result_path"]).exists()


def test_existing_main_workflow_includes_performance_agent_after_ui_testing() -> None:
    graph_text = str(build_graph().get_graph().nodes)

    assert "api_testing" in graph_text
    assert "ui_testing" in graph_text
    assert "performance_testing" in graph_text


def test_dashboard_still_imports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app(testing=True)
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_mcp_self_test_still_imports() -> None:
    config = get_default_mcp_server_command()

    assert config["testing"]["transport"] == "stdio"
