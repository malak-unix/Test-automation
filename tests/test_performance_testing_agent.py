from __future__ import annotations

import json
from pathlib import Path

from test_auto.agents import performance_testing_agent
from test_auto.agents.performance_testing_agent import (
    performance_testing_node,
    run_performance_testing_agent_alone,
)


def fake_performance_plan() -> dict:
    return {
        "performance_tests": [
            {
                "id": "PERF_001",
                "name": "todo_list_perf",
                "endpoint": "/api/todos/",
                "method": "GET",
                "users": 1,
                "spawn_rate": 1,
                "duration_seconds": 1,
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


def test_run_performance_testing_agent_alone_no_tests(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        performance_testing_agent,
        "build_performance_tests_from_plan",
        lambda *args, **kwargs: [],
    )

    result = run_performance_testing_agent_alone(
        target_url="http://localhost:8000",
        test_plan={},
        run_id="perf_no_tests",
    )

    assert result["performance_results"]["status"] == "partial"
    assert Path(result["performance_result_path"]).exists()


def test_run_performance_testing_agent_alone_mocked_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        performance_testing_agent,
        "execute_performance_test_case",
        mocked_performance_result,
    )

    result = run_performance_testing_agent_alone(
        target_url="http://localhost:8000",
        test_plan=fake_performance_plan(),
        run_id="perf_mocked",
    )

    assert result["run_id"] == "perf_mocked"
    assert Path(result["performance_result_path"]).exists()
    assert result["summary"]["total_tests"] == 1
    assert result["performance_artifacts"]


def test_performance_testing_node_returns_state_patch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        performance_testing_agent,
        "execute_performance_test_case",
        mocked_performance_result,
    )

    patch = performance_testing_node(
        {
            "run_id": "perf_node",
            "target_url": "http://localhost:8000",
            "test_plan": fake_performance_plan(),
            "user_preferences": {},
            "errors": [],
            "agent_logs": [],
        }
    )

    assert patch["performance_results"]
    assert patch["performance_result_path"]
    assert "performance_artifacts" in patch
    assert patch["agent_logs"]


def test_performance_testing_node_missing_target_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    patch = performance_testing_node(
        {
            "run_id": "perf_missing_target",
            "target_url": "",
            "test_plan": fake_performance_plan(),
            "user_preferences": {},
            "errors": [],
            "agent_logs": [],
        }
    )

    assert patch["performance_results"]["status"] == "error"
    assert patch["errors"]


def test_performance_agent_does_not_test_external_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_performance_testing_agent_alone(
        target_url="https://example.com",
        test_plan=fake_performance_plan(),
        run_id="perf_external_skip",
    )

    test_result = result["performance_results"]["tests"][0]
    assert test_result["status"] == "skipped"


def test_performance_agent_does_not_expose_secrets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_performance_testing_agent_alone(
        target_url="https://example.com",
        test_plan=fake_performance_plan(),
        run_id="perf_secret_masking",
        user_preferences={
            "password": "PASSWORD_SHOULD_NOT_APPEAR",
            "token": "TOKEN_SHOULD_NOT_APPEAR",
        },
    )

    payload = json.dumps(result)
    assert "PASSWORD_SHOULD_NOT_APPEAR" not in payload
    assert "TOKEN_SHOULD_NOT_APPEAR" not in payload
