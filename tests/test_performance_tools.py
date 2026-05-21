from __future__ import annotations

import subprocess
from pathlib import Path

from test_auto.tools import performance_tools
from test_auto.tools.performance_tools import (
    build_performance_tests_from_plan,
    clamp_load_settings,
    compute_performance_summary,
    create_locustfile_content,
    execute_performance_test_case,
    is_local_target,
    is_safe_performance_method,
    normalize_performance_endpoint,
    run_locust_subprocess,
)


def test_is_local_target() -> None:
    assert is_local_target("http://localhost:8000")
    assert is_local_target("http://127.0.0.1:8000")
    assert not is_local_target("https://example.com")


def test_normalize_performance_endpoint() -> None:
    assert normalize_performance_endpoint(None) == "/"
    assert normalize_performance_endpoint("api/todos/") == "/api/todos/"


def test_is_safe_performance_method() -> None:
    assert is_safe_performance_method("GET")
    assert is_safe_performance_method("HEAD")
    assert not is_safe_performance_method("POST")


def test_clamp_load_settings() -> None:
    settings = clamp_load_settings(users=100, spawn_rate=2, duration_seconds=999)

    assert settings["users"] == 20
    assert settings["duration_seconds"] == 60
    assert settings["spawn_rate"] == 2
    assert settings["warnings"]


def test_build_performance_tests_from_plan() -> None:
    tests = build_performance_tests_from_plan(
        {
            "performance_tests": [
                {
                    "id": "PERF_001",
                    "name": "todo_list_perf",
                    "endpoint": "/api/todos/",
                    "method": "GET",
                }
            ]
        }
    )

    assert tests[0]["id"] == "PERF_001"
    assert tests[0]["endpoint"] == "/api/todos/"


def test_build_performance_tests_infers_from_api_get() -> None:
    tests = build_performance_tests_from_plan(
        {
            "api_tests": [
                {
                    "id": "API_001",
                    "name": "list_todos",
                    "method": "GET",
                    "endpoint": "/api/todos/",
                }
            ]
        }
    )

    assert tests[0]["method"] == "GET"
    assert tests[0]["endpoint"] == "/api/todos/"


def test_create_locustfile_content() -> None:
    content = create_locustfile_content(
        {"id": "PERF_001", "endpoint": "/api/todos/", "method": "GET"}
    )

    assert "HttpUser" in content
    assert "/api/todos/" in content


def test_execute_performance_test_case_skips_external_target_by_default() -> None:
    result = execute_performance_test_case(
        target_url="https://example.com",
        test_case={"id": "PERF_001", "endpoint": "/", "method": "GET"},
        run_id="external_skip",
    )

    assert result["status"] == "skipped"
    assert "External performance targets" in result["details"]


def test_execute_performance_test_case_skips_mutating_method(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = execute_performance_test_case(
        target_url="http://localhost:8000",
        test_case={"id": "PERF_001", "endpoint": "/api/todos/", "method": "POST"},
        run_id="mutating_skip",
    )

    assert result["status"] == "skipped"
    assert "GET and HEAD" in result["details"]


def test_run_locust_subprocess_missing_locust(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    locustfile = tmp_path / "locustfile.py"
    locustfile.write_text("from locust import HttpUser\n", encoding="utf-8")

    def raise_missing(*args, **kwargs):
        raise FileNotFoundError("locust")

    monkeypatch.setattr(subprocess, "run", raise_missing)

    result = run_locust_subprocess(
        locustfile_path=str(locustfile),
        target_url="http://localhost:8000",
        users=1,
        spawn_rate=1,
        duration_seconds=1,
        run_id="missing_locust",
        test_id="PERF_001",
    )

    assert result["status"] == "error"
    assert result["error_type"] == "configuration_error"


def test_run_locust_subprocess_nonzero_with_csv_is_parsed_as_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    locustfile = tmp_path / "locustfile.py"
    locustfile.write_text("from locust import HttpUser\n", encoding="utf-8")

    def fake_run(*args, **kwargs):
        csv_path = (
            tmp_path
            / "results"
            / "runs"
            / "locust_http_failures"
            / "performance"
            / "PERF_001_stats.csv"
        )
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(
            "Type,Name,Request Count,Failure Count,Average Response Time,Min Response Time,Max Response Time,Requests/s,50%,95%\n"
            "GET,/missing/,4,4,10,8,12,1,10,12\n"
            ",Aggregated,4,4,10,8,12,1,10,12\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="HTTP failures")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_locust_subprocess(
        locustfile_path=str(locustfile),
        target_url="http://localhost:8000",
        users=1,
        spawn_rate=1,
        duration_seconds=1,
        run_id="locust_http_failures",
        test_id="PERF_001",
    )

    assert result["status"] == "success"
    assert "HTTP failures" in result["error"]


def test_execute_performance_test_case_zero_requests_environment_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        performance_tools,
        "run_locust_subprocess",
        lambda **kwargs: {
            "status": "success",
            "csv_prefix": "results/runs/zero_requests/performance/PERF_001",
            "error": None,
        },
    )
    monkeypatch.setattr(
        performance_tools,
        "parse_locust_csv",
        lambda csv_prefix: {
            "metrics": {"total_requests": 0, "failures": 0, "failure_rate": 0.0},
            "error": None,
        },
    )

    result = execute_performance_test_case(
        target_url="http://localhost:8000",
        test_case={"id": "PERF_001", "endpoint": "/", "method": "GET"},
        run_id="zero_requests",
    )

    assert result["status"] == "environment_error"


def test_compute_performance_summary() -> None:
    summary = compute_performance_summary(
        [
            {"status": "passed", "average_response_time_ms": 100, "p95_response_time_ms": 200, "failure_rate": 0},
            {"status": "performance_threshold_failed", "average_response_time_ms": 300, "p95_response_time_ms": 600, "failure_rate": 2},
            {"status": "skipped"},
            {"status": "configuration_error"},
        ]
    )

    assert summary["total_tests"] == 4
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
    assert summary["errors"] == 1
    assert summary["average_response_time_ms"] == 200
