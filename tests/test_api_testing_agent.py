from __future__ import annotations

import json
from pathlib import Path

from test_auto.agents import api_testing_agent
from test_auto.agents.api_testing_agent import (
    api_testing_node,
    extract_api_tests,
    load_test_plan_file,
    load_test_plan_from_run_dir,
    run_api_testing_agent_alone,
)


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


def fake_execution_result(test_case: dict) -> dict:
    return {
        "id": test_case["id"],
        "name": test_case["name"],
        "method": test_case["method"],
        "endpoint": test_case["endpoint"],
        "status": "passed",
        "expected_status": test_case.get("expected_status"),
        "actual_status": 200,
        "duration_ms": 12.0,
        "details": "mocked",
        "evidence": {
            "url": "http://localhost:8000/api/todos/",
            "method": "GET",
            "request_body": None,
            "response_preview": "{\"ok\": true}",
            "response_json_preview": {"ok": "True"},
        },
        "assertions": [{"type": "status_code", "passed": True}],
        "error_type": None,
    }


def test_extract_api_tests() -> None:
    assert extract_api_tests(sample_test_plan()) == sample_test_plan()["api_tests"]


def test_run_api_testing_agent_alone_no_api_tests(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_api_testing_agent_alone("http://localhost:8000", {"api_tests": []})

    assert result["api_results"]["status"] == "partial"
    assert Path(result["api_result_path"]).exists()


def test_run_api_testing_agent_alone_with_mocked_requests(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        api_testing_agent,
        "execute_api_test_case",
        lambda target_url, test_case, auth_token=None, timeout_seconds=5: fake_execution_result(test_case),
    )

    result = run_api_testing_agent_alone("http://localhost:8000", sample_test_plan())

    assert result["run_id"]
    assert result["api_results"]
    assert Path(result["api_result_path"]).exists()
    assert result["summary"]["total_tests"] > 0


def test_api_testing_node_returns_state_patch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        api_testing_agent,
        "execute_api_test_case",
        lambda target_url, test_case, auth_token=None, timeout_seconds=5: fake_execution_result(test_case),
    )

    update = api_testing_node(
        {
            "run_id": "test_run",
            "target_url": "http://localhost:8000",
            "test_plan": sample_test_plan(),
            "user_preferences": {},
            "errors": [],
            "agent_logs": [],
        }
    )

    assert update["api_results"]
    assert update["api_result_path"]
    assert update["agent_logs"]


def test_api_testing_node_missing_target_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    update = api_testing_node(
        {
            "run_id": "test_run",
            "target_url": "",
            "test_plan": sample_test_plan(),
            "user_preferences": {},
            "errors": [],
            "agent_logs": [],
        }
    )

    assert update["errors"]
    assert update["api_results"]["status"] == "error"


def test_api_agent_does_not_expose_auth_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_api_testing_agent_alone(
        "http://localhost:8000",
        {
            "api_tests": [
                {
                    "id": "API_001",
                    "name": "dynamic",
                    "method": "GET",
                    "endpoint": "/api/todos/<int:pk>/",
                }
            ]
        },
        user_preferences={"auth_token": "placeholder-token"},
    )

    assert "placeholder-token" not in json.dumps(result["api_results"])


def test_api_agent_cli_helpers_if_present(tmp_path: Path) -> None:
    run_dir = tmp_path / "results" / "runs" / "run_1"
    run_dir.mkdir(parents=True)
    path = run_dir / "test_plan.json"
    path.write_text(json.dumps(sample_test_plan()), encoding="utf-8")

    assert load_test_plan_file(path)["api_tests"]
    assert load_test_plan_from_run_dir(run_dir)["api_tests"]
