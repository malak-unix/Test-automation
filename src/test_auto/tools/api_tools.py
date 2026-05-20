"""Deterministic HTTP helpers for the standalone API Testing Agent."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import requests

from test_auto.shared.utils import ensure_directory, write_json_file


SUPPORTED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
SENSITIVE_HEADER_NAMES = {
    "authorization",
    "token",
    "cookie",
    "set-cookie",
    "x-api-key",
}
SENSITIVE_BODY_KEYS = {
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "api_key",
}
MASK = "***MASKED***"
MAX_RESPONSE_PREVIEW_CHARS = 500


def join_url(base_url: str, endpoint: str) -> str:
    """Join a target base URL and API endpoint without duplicate slashes."""

    if endpoint.startswith(("http://", "https://")):
        return endpoint
    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


def is_endpoint_executable(endpoint: str) -> bool:
    """Return False for endpoints that still contain unresolved path params."""

    return not bool(re.search(r"<[^>]+>|{[^}]+}|(^|/):[^/]+", endpoint or ""))


def mask_sensitive_headers(headers: dict[str, Any] | None) -> dict[str, Any]:
    """Mask sensitive header values before saving or displaying them."""

    masked: dict[str, Any] = {}
    for key, value in (headers or {}).items():
        if key.lower() in SENSITIVE_HEADER_NAMES:
            masked[key] = MASK
        else:
            masked[key] = value
    return masked


def _mask_sensitive_body(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: MASK if str(key).lower() in SENSITIVE_BODY_KEYS else _mask_sensitive_body(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask_sensitive_body(item) for item in value]
    return value


def build_headers(
    auth_token: str | None = None,
    extra_headers: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build HTTP headers for requests without logging secrets."""

    headers: dict[str, str] = {"Accept": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    for key, value in (extra_headers or {}).items():
        headers[str(key)] = str(value)
    return headers


def _preview_text(text: str | None) -> str:
    return (text or "")[:MAX_RESPONSE_PREVIEW_CHARS]


def _preview_json(value: Any) -> dict[str, Any] | list[Any] | None:
    if isinstance(value, dict):
        return {
            key: _preview_text(str(item)) if not isinstance(item, (dict, list)) else "<nested>"
            for key, item in list(value.items())[:20]
        }
    if isinstance(value, list):
        return value[:5]
    return None


def send_http_request(
    method: str,
    url: str,
    headers: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    """Send one HTTP request and return a compact, non-throwing result."""

    started = time.perf_counter()
    method_upper = method.upper()
    if method_upper not in SUPPORTED_HTTP_METHODS:
        return {
            "ok": False,
            "status_code": None,
            "duration_ms": 0.0,
            "text_preview": "",
            "json_preview": None,
            "error": f"Unsupported HTTP method: {method_upper}",
            "error_type": "test_data_error",
        }

    try:
        response = requests.request(
            method_upper,
            url,
            headers=headers,
            json=json_body,
            timeout=timeout_seconds,
        )
        duration_ms = (time.perf_counter() - started) * 1000
        json_preview = None
        try:
            json_preview = _preview_json(response.json())
        except ValueError:
            json_preview = None
        return {
            "ok": True,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "text_preview": _preview_text(response.text),
            "json_preview": json_preview,
            "error": None,
            "error_type": None,
        }
    except requests.exceptions.Timeout as error:
        return {
            "ok": False,
            "status_code": None,
            "duration_ms": (time.perf_counter() - started) * 1000,
            "text_preview": "",
            "json_preview": None,
            "error": str(error),
            "error_type": "environment_error",
        }
    except requests.exceptions.RequestException as error:
        return {
            "ok": False,
            "status_code": None,
            "duration_ms": (time.perf_counter() - started) * 1000,
            "text_preview": "",
            "json_preview": None,
            "error": str(error),
            "error_type": "environment_error",
        }


def evaluate_status_assertion(
    expected_status: int | None,
    actual_status: int | None,
) -> dict[str, Any]:
    """Evaluate the expected HTTP status code when one is provided."""

    if expected_status is None:
        return {
            "type": "status_code",
            "passed": True,
            "status": "skipped",
            "details": "No expected status provided; status assertion skipped.",
        }
    passed = expected_status == actual_status
    return {
        "type": "status_code",
        "passed": passed,
        "status": "passed" if passed else "failed",
        "details": f"Expected {expected_status}, got {actual_status}.",
    }


def evaluate_response_assertions(
    response_result: dict[str, Any],
    assertions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Evaluate supported response assertions without throwing."""

    evaluated = []
    for assertion in assertions:
        assertion_type = assertion.get("type")
        expected = assertion.get("expected")
        if assertion_type == "status_code":
            try:
                expected_status = int(expected)
            except (TypeError, ValueError):
                expected_status = None
            evaluated.append(
                evaluate_status_assertion(
                    expected_status,
                    response_result.get("status_code"),
                )
            )
        elif assertion_type == "response_contains":
            expected_text = str(expected or "")
            passed = expected_text in str(response_result.get("text_preview", ""))
            evaluated.append(
                {
                    "type": "response_contains",
                    "passed": passed,
                    "status": "passed" if passed else "failed",
                    "details": f"Expected response preview to contain '{expected_text}'.",
                }
            )
        elif assertion_type == "response_schema":
            wants_json = assertion.get("target") == "json" or "json" in str(expected).lower()
            passed = bool(response_result.get("json_preview")) if wants_json else True
            evaluated.append(
                {
                    "type": "response_schema",
                    "passed": passed,
                    "status": "passed" if passed else "failed",
                    "details": "Checked that response is JSON." if wants_json else "Schema assertion skipped.",
                }
            )
        else:
            evaluated.append(
                {
                    "type": assertion_type or "unknown",
                    "passed": True,
                    "status": "skipped",
                    "details": "Unsupported assertion type skipped by API agent.",
                }
            )
    return evaluated


def execute_api_test_case(
    target_url: str,
    test_case: dict[str, Any],
    auth_token: str | None = None,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    """Execute one planned API test case and return a schema-compatible dict."""

    method = str(test_case.get("method") or "UNKNOWN").upper()
    endpoint = str(test_case.get("endpoint") or "")
    expected_status = test_case.get("expected_status")
    evidence = {
        "url": join_url(target_url, endpoint),
        "method": method,
        "request_body": _mask_sensitive_body(test_case.get("request_body")),
        "response_preview": None,
        "response_json_preview": None,
    }

    base_result = {
        "id": str(test_case.get("id") or "API_UNKNOWN"),
        "name": str(test_case.get("name") or "unnamed_api_test"),
        "method": method,
        "endpoint": endpoint,
        "expected_status": expected_status,
        "actual_status": None,
        "duration_ms": None,
        "evidence": evidence,
        "assertions": [],
        "error_type": None,
    }

    if not is_endpoint_executable(endpoint):
        return {
            **base_result,
            "status": "skipped",
            "details": "Endpoint contains unresolved dynamic path parameters.",
        }
    if method == "UNKNOWN":
        return {
            **base_result,
            "status": "skipped",
            "details": "HTTP method is UNKNOWN and cannot be safely executed.",
        }

    headers = build_headers(auth_token=auth_token)
    response = send_http_request(
        method=method,
        url=evidence["url"],
        headers=headers,
        json_body=test_case.get("request_body"),
        timeout_seconds=timeout_seconds,
    )
    evidence.update(
        {
            "response_preview": response.get("text_preview"),
            "response_json_preview": response.get("json_preview"),
        }
    )
    if not response["ok"]:
        error_type = response.get("error_type") or "error"
        return {
            **base_result,
            "status": error_type,
            "actual_status": response.get("status_code"),
            "duration_ms": response.get("duration_ms"),
            "details": response.get("error"),
            "evidence": evidence,
            "error_type": error_type,
        }

    evaluated_assertions = [
        evaluate_status_assertion(expected_status, response.get("status_code")),
        *evaluate_response_assertions(response, test_case.get("assertions") or []),
    ]
    failed_assertions = [
        item for item in evaluated_assertions if item.get("passed") is False
    ]
    return {
        **base_result,
        "status": "assertion_error" if failed_assertions else "passed",
        "actual_status": response.get("status_code"),
        "duration_ms": response.get("duration_ms"),
        "details": (
            failed_assertions[0]["details"]
            if failed_assertions
            else "API test executed successfully."
        ),
        "evidence": evidence,
        "assertions": evaluated_assertions,
        "error_type": "assertion_error" if failed_assertions else None,
    }


def compute_api_summary(test_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate API execution counts and pass rate."""

    total = len(test_results)
    passed = sum(item.get("status") == "passed" for item in test_results)
    skipped = sum(item.get("status") == "skipped" for item in test_results)
    failed = sum(item.get("status") in {"failed", "assertion_error"} for item in test_results)
    errors = sum(
        item.get("status") in {"error", "environment_error", "test_data_error"}
        for item in test_results
    )
    return {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
    }


def save_api_result(
    run_id: str,
    api_output: dict[str, Any],
    results_dir: str = "results",
) -> str:
    """Save results/runs/<run_id>/api_result.json."""

    run_dir = ensure_directory(Path(results_dir) / "runs" / run_id)
    path = write_json_file(run_dir / "api_result.json", api_output)
    return str(path)

