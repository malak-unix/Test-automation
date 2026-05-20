"""API Testing Agent.

Role in the architecture: execute planned API test cases against target_url,
compare responses with planned assertions, and save api_result.json. It skips
unsafe methods by default and never invents endpoints.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from test_auto.graph.state import TestAutomationState
from test_auto.mcp.tool_router import build_mcp_agent_log, call_mcp_or_local, should_use_mcp
from test_auto.shared.schemas import APITestExecutionResult, APITestingOutput, APITestSummary
from test_auto.shared.utils import current_timestamp, generate_run_id
from test_auto.tools.bug_tools import mask_sensitive_values
from test_auto.tools.api_tools import (
    MASK,
    build_headers,
    compute_api_summary,
    evaluate_response_assertions,
    evaluate_status_assertion,
    execute_api_test_case,
    is_endpoint_executable,
    join_url,
    save_api_result,
    send_http_request,
)


API_TESTING_AGENT_SYSTEM_PROMPT = """
You are the API Testing Agent.
Execute only API test cases from the test_plan using HTTP tools.
Compare actual status, response body, and timing with expected values.
Do not invent endpoints.
Do not silently ignore failures.
Classify unreachable target as environment_error, not application_bug.
Return structured JSON.
"""

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SAFE_MODE_SKIP_DETAILS = "Skipped because mutating API tests are disabled by default."


def extract_api_tests(test_plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return API test case plans from a structured test_plan."""

    api_tests = (test_plan or {}).get("api_tests") or []
    return list(api_tests) if isinstance(api_tests, list) else []


def _skipped_mutating_result(test_case: dict[str, Any]) -> dict[str, Any]:
    method = str(test_case.get("method") or "UNKNOWN").upper()
    endpoint = str(test_case.get("endpoint") or "")
    return {
        "id": str(test_case.get("id") or "API_UNKNOWN"),
        "name": str(test_case.get("name") or "unnamed_api_test"),
        "method": method,
        "endpoint": endpoint,
        "status": "skipped",
        "expected_status": test_case.get("expected_status"),
        "actual_status": None,
        "duration_ms": None,
        "details": SAFE_MODE_SKIP_DETAILS,
        "evidence": {
            "url": endpoint,
            "method": method,
            "request_body": None,
            "response_preview": None,
            "response_json_preview": None,
        },
        "assertions": [],
        "error_type": None,
    }


def filter_api_tests_for_safe_mode(
    api_tests: list[dict[str, Any]],
    allow_mutating: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split planned API tests into executable tests and safety-mode skips."""

    if allow_mutating:
        return api_tests, []

    executable: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for test_case in api_tests:
        method = str(test_case.get("method") or "UNKNOWN").upper()
        if method in MUTATING_METHODS:
            skipped.append(_skipped_mutating_result(test_case))
        else:
            executable.append(test_case)
    return executable, skipped


def _output_status(summary: dict[str, Any], tests: list[dict[str, Any]]) -> str:
    if not tests:
        return "partial"
    if summary["errors"] == summary["total_tests"]:
        return "partial"
    if summary["passed"] == summary["total_tests"]:
        return "success"
    return "partial"


def _build_output(
    status: str,
    duration_seconds: float,
    summary: dict[str, Any],
    tests: list[dict[str, Any]],
    anomalies: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> APITestingOutput:
    return APITestingOutput(
        timestamp=current_timestamp(),
        status=status,
        duration_seconds=duration_seconds,
        summary=APITestSummary(**summary),
        tests=[APITestExecutionResult(**item) for item in tests],
        anomalies=anomalies or [],
        metadata=metadata or {},
    )


def _tool_backend(events: list[dict[str, Any]]) -> str:
    if any(event.get("fallback_used") for event in events):
        return "mixed"
    if not events or not any(event.get("used_mcp") for event in events):
        return "local"
    return "mcp"


def _normalize_mcp_http_response(response: dict[str, Any]) -> dict[str, Any]:
    status = response.get("status")
    return {
        "ok": status == "success",
        "status_code": response.get("status_code"),
        "duration_ms": response.get("duration_ms"),
        "text_preview": response.get("text_preview", ""),
        "json_preview": response.get("json_preview"),
        "error": response.get("error") or response.get("details"),
        "error_type": response.get("error_type") or (None if status == "success" else status),
    }


def _execute_api_test_case_with_optional_mcp(
    target_url: str,
    test_case: dict[str, Any],
    user_preferences: dict[str, Any],
    auth_token: str | None,
    timeout_seconds: int,
    allow_mutating: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not should_use_mcp(user_preferences):
        return (
            execute_api_test_case(
                target_url=target_url,
                test_case=test_case,
                auth_token=auth_token,
                timeout_seconds=timeout_seconds,
            ),
            [],
        )

    method = str(test_case.get("method") or "UNKNOWN").upper()
    endpoint = str(test_case.get("endpoint") or "")
    expected_status = test_case.get("expected_status")
    evidence = {
        "url": join_url(target_url, endpoint),
        "method": method,
        "request_body": mask_sensitive_values(test_case.get("request_body")),
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
        return (
            {
                **base_result,
                "status": "skipped",
                "details": "Endpoint contains unresolved dynamic path parameters.",
            },
            [],
        )
    if method == "UNKNOWN":
        return (
            {
                **base_result,
                "status": "skipped",
                "details": "HTTP method is UNKNOWN and cannot be safely executed.",
            },
            [],
        )

    headers = build_headers(auth_token=auth_token)
    routed = call_mcp_or_local(
        tool_name="send_http_request_tool",
        mcp_args={
            "method": method,
            "url": evidence["url"],
            "json_body": test_case.get("request_body"),
            "headers": headers,
            "timeout_seconds": timeout_seconds,
            "allow_mutating": allow_mutating,
        },
        local_callable=send_http_request,
        local_args={
            "method": method,
            "url": evidence["url"],
            "headers": headers,
            "json_body": test_case.get("request_body"),
            "timeout_seconds": timeout_seconds,
        },
        user_preferences=user_preferences,
    )
    raw_response = routed.get("result") or {}
    response = (
        _normalize_mcp_http_response(raw_response)
        if routed.get("used_mcp")
        else raw_response
    )
    event = build_mcp_agent_log(
        "send_http_request_tool",
        used_mcp=routed.get("used_mcp", False),
        fallback_used=routed.get("fallback_used", False),
        error=routed.get("mcp_error") or routed.get("error"),
    )
    evidence.update(
        {
            "response_preview": response.get("text_preview"),
            "response_json_preview": response.get("json_preview"),
        }
    )
    if not response.get("ok"):
        error_type = response.get("error_type") or "error"
        return (
            {
                **base_result,
                "status": error_type,
                "actual_status": response.get("status_code"),
                "duration_ms": response.get("duration_ms"),
                "details": response.get("error"),
                "evidence": evidence,
                "error_type": error_type,
            },
            [event],
        )

    evaluated_assertions = [
        evaluate_status_assertion(expected_status, response.get("status_code")),
        *evaluate_response_assertions(response, test_case.get("assertions") or []),
    ]
    failed_assertions = [item for item in evaluated_assertions if item.get("passed") is False]
    return (
        {
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
        },
        [event],
    )


def run_api_testing_agent_alone(
    target_url: str,
    test_plan: dict[str, Any],
    run_id: str | None = None,
    user_preferences: dict[str, Any] | None = None,
    auth_token: str | None = None,
    allow_mutating: bool = True,
) -> dict[str, Any]:
    """Execute planned API tests against target_url and save api_result.json."""

    started = time.perf_counter()
    active_run_id = run_id or generate_run_id()
    preferences = user_preferences or {}
    timeout_seconds = int(preferences.get("api_timeout_seconds") or 5)
    effective_auth_token = auth_token or preferences.get("auth_token")
    tool_backend = "local"
    mcp_fallback_used = False
    mcp_events: list[dict[str, Any]] = []

    if not target_url:
        summary = compute_api_summary([])
        error = {
            "agent": "api_testing",
            "field": "target_url",
            "message": "target_url is required for API testing.",
        }
        output = _build_output(
            status="error",
            duration_seconds=time.perf_counter() - started,
            summary=summary,
            tests=[],
            anomalies=[error],
            metadata={
                "target_url": target_url,
                "auth_token_used": bool(effective_auth_token),
                "tool_backend": tool_backend,
                "mcp_fallback_used": mcp_fallback_used,
                "mcp_events": mcp_events,
            },
        )
        output_data = output.model_dump(mode="json")
        api_result_path = save_api_result(active_run_id, output_data)
        return {
            "run_id": active_run_id,
            "api_results": output_data,
            "api_result_path": api_result_path,
            "summary": summary,
            "errors": [error],
            "agent_output": output_data,
        }

    api_tests = extract_api_tests(test_plan)
    if not api_tests:
        summary = compute_api_summary([])
        anomaly = {
            "agent": "api_testing",
            "message": "No API tests found in test_plan.",
        }
        output = _build_output(
            status="partial",
            duration_seconds=time.perf_counter() - started,
            summary=summary,
            tests=[],
            anomalies=[anomaly],
            metadata={
                "target_url": target_url,
                "auth_token_used": bool(effective_auth_token),
                "tool_backend": tool_backend,
                "mcp_fallback_used": mcp_fallback_used,
                "mcp_events": mcp_events,
            },
        )
        output_data = output.model_dump(mode="json")
        api_result_path = save_api_result(active_run_id, output_data)
        return {
            "run_id": active_run_id,
            "api_results": output_data,
            "api_result_path": api_result_path,
            "summary": summary,
            "errors": [],
            "agent_output": output_data,
        }

    executable_tests, skipped_tests = filter_api_tests_for_safe_mode(
        api_tests,
        allow_mutating=allow_mutating,
    )
    executed_tests = []
    for test_case in executable_tests:
        test_result, events = _execute_api_test_case_with_optional_mcp(
            target_url=target_url,
            test_case=test_case,
            user_preferences=preferences,
            auth_token=effective_auth_token,
            timeout_seconds=timeout_seconds,
            allow_mutating=allow_mutating,
        )
        executed_tests.append(test_result)
        mcp_events.extend(events)
    tool_backend = _tool_backend(mcp_events)
    mcp_fallback_used = any(event.get("fallback_used") for event in mcp_events)
    tests = [*skipped_tests, *executed_tests]
    summary = compute_api_summary(tests)
    output = _build_output(
        status=_output_status(summary, tests),
        duration_seconds=time.perf_counter() - started,
        summary=summary,
        tests=tests,
        metadata={
            "target_url": target_url,
            "auth_token_used": bool(effective_auth_token),
            "allow_mutating_api_tests": bool(allow_mutating),
            "timeout_seconds": timeout_seconds,
            "tool_backend": tool_backend,
            "mcp_fallback_used": mcp_fallback_used,
            "mcp_events": mcp_events,
        },
    )
    output_data = output.model_dump(mode="json")
    api_result_path = save_api_result(active_run_id, output_data)
    return {
        "run_id": active_run_id,
        "api_results": output_data,
        "api_result_path": api_result_path,
        "summary": summary,
        "errors": [],
        "agent_output": output_data,
    }


def api_testing_node(state: TestAutomationState) -> dict[str, Any]:
    """LangGraph node that returns a partial State update for API testing."""

    active_run_id = state.get("run_id") or generate_run_id()
    preferences = state.get("user_preferences") or {}
    allow_mutating = bool(preferences.get("allow_mutating_api_tests", False))
    result = run_api_testing_agent_alone(
        target_url=state.get("target_url", ""),
        test_plan=state.get("test_plan") or {},
        run_id=active_run_id,
        user_preferences=preferences,
        auth_token=preferences.get("auth_token"),
        allow_mutating=allow_mutating,
    )
    sanitized_preferences = dict(preferences)
    if "auth_token" in sanitized_preferences:
        sanitized_preferences["auth_token"] = MASK
    return {
        "run_id": result["run_id"],
        "user_preferences": sanitized_preferences,
        "api_results": result["api_results"],
        "api_result_path": result["api_result_path"],
        "agent_logs": [*state.get("agent_logs", []), result["agent_output"]],
        "errors": [*state.get("errors", []), *result.get("errors", [])],
    }


def load_test_plan_file(path: str | Path) -> dict[str, Any]:
    """Load a test_plan JSON file."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_test_plan_from_run_dir(run_dir: str | Path) -> dict[str, Any]:
    """Load test_plan.json from a previous run directory."""

    return load_test_plan_file(Path(run_dir) / "test_plan.json")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the API Testing Agent alone.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-dir", default=None)
    source.add_argument("--test-plan", default=None)
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--auth-token", default=None)
    return parser.parse_args()


def _compact_cli_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": result.get("run_id"),
        "summary": result.get("summary"),
        "api_result_path": result.get("api_result_path"),
        "errors": result.get("errors", []),
    }


def main() -> None:
    """CLI entry point for standalone API testing."""

    args = _parse_args()
    if args.run_dir:
        test_plan = load_test_plan_from_run_dir(args.run_dir)
        run_id = Path(args.run_dir).name
    else:
        test_plan = load_test_plan_file(args.test_plan)
        parent = Path(args.test_plan).parent
        run_id = parent.name if parent.name else None

    result = run_api_testing_agent_alone(
        target_url=args.target_url,
        test_plan=test_plan,
        run_id=run_id,
        auth_token=args.auth_token,
    )
    print(json.dumps(_compact_cli_result(result), indent=2))


if __name__ == "__main__":
    main()
