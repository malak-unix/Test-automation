from __future__ import annotations

from test_auto.tools.api_tools import (
    build_headers,
    compute_api_summary,
    evaluate_response_assertions,
    evaluate_status_assertion,
    execute_api_test_case,
    is_endpoint_executable,
    join_url,
    mask_sensitive_headers,
    send_http_request,
)
import requests


def test_join_url() -> None:
    assert join_url("http://localhost:8000", "/api/todos/") == "http://localhost:8000/api/todos/"


def test_is_endpoint_executable() -> None:
    assert is_endpoint_executable("/api/todos/")
    assert not is_endpoint_executable("/api/todos/<int:pk>/")
    assert not is_endpoint_executable("/api/todos/{id}/")
    assert not is_endpoint_executable("/api/todos/:id/")


def test_mask_sensitive_headers() -> None:
    masked = mask_sensitive_headers(
        {
            "Authorization": "Bearer secret",
            "Cookie": "session=secret",
            "X-API-Key": "secret",
            "Accept": "application/json",
        }
    )

    assert masked["Authorization"] == "***MASKED***"
    assert masked["Cookie"] == "***MASKED***"
    assert masked["X-API-Key"] == "***MASKED***"
    assert masked["Accept"] == "application/json"


def test_build_headers_without_token() -> None:
    headers = build_headers()

    assert headers["Accept"] == "application/json"
    assert "Authorization" not in headers


def test_build_headers_with_token_masks_in_saved_evidence() -> None:
    headers = build_headers(auth_token="placeholder-token")
    masked = mask_sensitive_headers(headers)

    assert headers["Authorization"] == "Bearer placeholder-token"
    assert masked["Authorization"] == "***MASKED***"


def test_evaluate_status_assertion_pass() -> None:
    result = evaluate_status_assertion(200, 200)

    assert result["passed"]


def test_evaluate_status_assertion_fail() -> None:
    result = evaluate_status_assertion(201, 400)

    assert not result["passed"]


def test_evaluate_response_assertions_response_contains() -> None:
    result = evaluate_response_assertions(
        {"text_preview": "todo created", "json_preview": None},
        [{"type": "response_contains", "expected": "todo"}],
    )

    assert result[0]["passed"]


def test_execute_api_test_case_skips_dynamic_endpoint() -> None:
    result = execute_api_test_case(
        "http://localhost:8000",
        {
            "id": "API_001",
            "name": "detail",
            "method": "GET",
            "endpoint": "/api/todos/<int:pk>/",
        },
    )

    assert result["status"] == "skipped"


def test_compute_api_summary() -> None:
    summary = compute_api_summary(
        [
            {"status": "passed"},
            {"status": "assertion_error"},
            {"status": "skipped"},
            {"status": "environment_error"},
        ]
    )

    assert summary["total_tests"] == 4
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
    assert summary["errors"] == 1
    assert summary["pass_rate"] == 25.0


def test_send_http_request_connection_error_is_environment_error(monkeypatch) -> None:
    def raise_connection_error(*args, **kwargs):
        raise requests.exceptions.ConnectionError("connection refused")

    monkeypatch.setattr(requests, "request", raise_connection_error)

    result = send_http_request("GET", "http://localhost:8000/api/todos/")

    assert not result["ok"]
    assert result["error_type"] == "environment_error"
