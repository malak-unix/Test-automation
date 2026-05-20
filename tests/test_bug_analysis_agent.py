from __future__ import annotations

import json
from pathlib import Path

from test_auto.agents.bug_analysis_agent import (
    bug_analysis_node,
    run_bug_analysis_agent_alone,
)
from test_auto.tools.bug_tools import load_bug_context_from_run_dir


def fake_api_results() -> dict:
    return {
        "agent": "api_testing",
        "status": "partial",
        "summary": {
            "total_tests": 5,
            "passed": 1,
            "failed": 2,
            "skipped": 1,
            "errors": 1,
            "pass_rate": 20.0,
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
                "duration_ms": 30.0,
                "details": "ok",
            },
            {
                "id": "API_002",
                "name": "target_down",
                "method": "GET",
                "endpoint": "/api/todos/",
                "status": "environment_error",
                "expected_status": 200,
                "actual_status": None,
                "duration_ms": 4.0,
                "details": "Connection refused",
            },
            {
                "id": "API_003",
                "name": "auth_required",
                "method": "GET",
                "endpoint": "/api/todos/",
                "status": "assertion_error",
                "expected_status": 401,
                "actual_status": 200,
                "duration_ms": 18.0,
                "details": "Expected 401, got 200.",
            },
            {
                "id": "API_004",
                "name": "server_error",
                "method": "GET",
                "endpoint": "/api/todos/",
                "status": "assertion_error",
                "expected_status": 200,
                "actual_status": 500,
                "duration_ms": 20.0,
                "details": "Expected 200, got 500.",
            },
            {
                "id": "API_005",
                "name": "dynamic_detail",
                "method": "GET",
                "endpoint": "/api/todos/<int:pk>/",
                "status": "skipped",
                "expected_status": None,
                "actual_status": None,
                "duration_ms": None,
                "details": "Endpoint contains unresolved dynamic path parameters.",
            },
        ],
    }


def test_run_bug_analysis_agent_alone_fake_api_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_bug_analysis_agent_alone(api_results=fake_api_results())

    assert result["run_id"]
    assert result["bug_results"]
    assert result["bug_result_path"]
    assert result["summary"]["total_anomalies"] >= 4
    assert Path(result["bug_result_path"]).exists()


def test_run_bug_analysis_agent_from_api_result_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    api_path = tmp_path / "api_result.json"
    api_path.write_text(json.dumps(fake_api_results()), encoding="utf-8")

    result = run_bug_analysis_agent_alone(api_result_path=str(api_path))

    assert Path(result["bug_result_path"]).exists()
    assert result["bug_results"]["anomalies"]


def test_run_bug_analysis_agent_from_run_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = Path("results") / "runs" / "bug_run"
    run_dir.mkdir(parents=True)
    (run_dir / "api_result.json").write_text(json.dumps(fake_api_results()), encoding="utf-8")

    result = run_bug_analysis_agent_alone(run_dir=str(run_dir))

    assert result["run_id"] == "bug_run"
    assert (run_dir / "bug_result.json").exists()


def test_bug_analysis_node_returns_state_patch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    update = bug_analysis_node(
        {
            "run_id": "test_run",
            "api_results": fake_api_results(),
            "errors": [],
            "agent_logs": [],
        }
    )

    assert update["bug_results"]
    assert update["bug_result_path"]
    assert update["recommendations"]
    assert update["agent_logs"]


def test_bug_analysis_handles_missing_api_results(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_bug_analysis_agent_alone()

    assert result["bug_results"]["status"] == "partial"
    assert result["summary"]["info"] >= 1
    assert Path(result["bug_result_path"]).exists()


def test_bug_analysis_does_not_expose_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    results = fake_api_results()
    results["tests"][1]["details"] = "Authorization failed with Bearer SECRET_TOKEN_SHOULD_NOT_APPEAR"

    result = run_bug_analysis_agent_alone(api_results=results)

    assert "SECRET_TOKEN_SHOULD_NOT_APPEAR" not in json.dumps(result["bug_results"])


def test_cli_helpers_if_present(tmp_path: Path) -> None:
    run_dir = tmp_path / "results" / "runs" / "bug_context_run"
    run_dir.mkdir(parents=True)
    (run_dir / "api_result.json").write_text(json.dumps(fake_api_results()), encoding="utf-8")
    (run_dir / "project_info.json").write_text(
        json.dumps({"language": "Python", "framework": "Django REST Framework"}),
        encoding="utf-8",
    )

    context = load_bug_context_from_run_dir(run_dir)

    assert context["run_id"] == "bug_context_run"
    assert context["api_results"]["tests"]
    assert context["project_info"]["framework"] == "Django REST Framework"
