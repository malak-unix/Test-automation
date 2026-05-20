"""Performance Testing Agent.

Role in the architecture: execute planned or safely inferred GET/HEAD load
checks with small Locust settings, save compact metrics, and skip external
targets unless explicitly allowed. It never runs destructive traffic.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from test_auto.graph.state import TestAutomationState
from test_auto.shared.schemas import (
    PerformanceSummary,
    PerformanceTestExecutionResult,
    PerformanceTestingOutput,
)
from test_auto.shared.utils import current_timestamp, generate_run_id
from test_auto.tools.bug_tools import mask_sensitive_values
from test_auto.tools.performance_tools import (
    build_performance_tests_from_plan,
    compute_performance_summary,
    execute_performance_test_case,
    save_performance_result,
)


PERFORMANCE_TESTING_AGENT_SYSTEM_PROMPT = """
You are the Performance Testing Agent.
Execute only safe performance tests against authorized targets.
Use small load settings by default.
Do not test external targets unless explicitly allowed.
Use GET or HEAD only.
Classify unavailable target or missing Locust as environment/configuration error.
Return structured JSON.
"""


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
    artifacts: list[dict[str, Any]] | None = None,
    anomalies: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> PerformanceTestingOutput:
    return PerformanceTestingOutput(
        timestamp=current_timestamp(),
        status=status,
        duration_seconds=duration_seconds,
        summary=PerformanceSummary(**summary),
        tests=[PerformanceTestExecutionResult(**item) for item in tests],
        artifacts=artifacts or [],
        anomalies=anomalies or [],
        metadata=metadata or {},
    )


def _collect_artifacts(test_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for test_result in test_results:
        for path in test_result.get("artifact_paths") or []:
            path_string = str(path)
            if path_string in seen:
                continue
            seen.add(path_string)
            artifacts.append(
                {
                    "test_id": test_result.get("id"),
                    "path": path_string,
                    "kind": "performance_artifact",
                }
            )
    return artifacts


def run_performance_testing_agent_alone(
    target_url: str,
    test_plan: dict[str, Any] | None = None,
    run_id: str | None = None,
    user_preferences: dict[str, Any] | None = None,
    discovered_endpoints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute safe performance tests and save performance_result.json."""

    started = time.perf_counter()
    active_run_id = run_id or generate_run_id()
    preferences = mask_sensitive_values(user_preferences or {})
    if not target_url:
        summary = compute_performance_summary([])
        error = {
            "agent": "performance_testing",
            "field": "target_url",
            "message": "target_url is required for performance testing.",
        }
        output = _build_output(
            status="error",
            duration_seconds=time.perf_counter() - started,
            summary=summary,
            tests=[],
            anomalies=[error],
            metadata={"target_url": target_url, "preferences": preferences},
        )
        output_data = output.model_dump(mode="json")
        performance_result_path = save_performance_result(active_run_id, output_data)
        return {
            "run_id": active_run_id,
            "performance_results": output_data,
            "performance_result_path": performance_result_path,
            "performance_artifacts": [],
            "summary": summary,
            "errors": [error],
            "agent_output": output_data,
        }

    performance_tests = build_performance_tests_from_plan(
        test_plan or {},
        discovered_endpoints=discovered_endpoints or [],
        user_preferences=preferences,
    )
    if not performance_tests:
        summary = compute_performance_summary([])
        anomaly = {
            "agent": "performance_testing",
            "message": "No performance tests available.",
        }
        output = _build_output(
            status="partial",
            duration_seconds=time.perf_counter() - started,
            summary=summary,
            tests=[],
            anomalies=[anomaly],
            metadata={"target_url": target_url, "preferences": preferences},
        )
        output_data = output.model_dump(mode="json")
        performance_result_path = save_performance_result(active_run_id, output_data)
        return {
            "run_id": active_run_id,
            "performance_results": output_data,
            "performance_result_path": performance_result_path,
            "performance_artifacts": [],
            "summary": summary,
            "errors": [],
            "agent_output": output_data,
        }

    test_results = [
        execute_performance_test_case(
            target_url=target_url,
            test_case=test_case,
            run_id=active_run_id,
            user_preferences=preferences,
        )
        for test_case in performance_tests
    ]
    artifacts = _collect_artifacts(test_results)
    summary = compute_performance_summary(test_results)
    output = _build_output(
        status=_output_status(summary, test_results),
        duration_seconds=time.perf_counter() - started,
        summary=summary,
        tests=test_results,
        artifacts=artifacts,
        metadata={
            "target_url": target_url,
            "safe_methods": ["GET", "HEAD"],
            "allow_external_performance_test": bool(
                preferences.get("allow_external_performance_test", False)
            ),
        },
    )
    output_data = output.model_dump(mode="json")
    performance_result_path = save_performance_result(active_run_id, output_data)
    return {
        "run_id": active_run_id,
        "performance_results": output_data,
        "performance_result_path": performance_result_path,
        "performance_artifacts": artifacts,
        "summary": summary,
        "errors": [],
        "agent_output": output_data,
    }


def performance_testing_node(state: TestAutomationState) -> dict[str, Any]:
    """LangGraph node that returns a partial State update for performance testing."""

    active_run_id = state.get("run_id") or generate_run_id()
    result = run_performance_testing_agent_alone(
        target_url=state.get("target_url", ""),
        test_plan=state.get("test_plan") or {},
        run_id=active_run_id,
        user_preferences=state.get("user_preferences") or {},
        discovered_endpoints=state.get("discovered_endpoints") or [],
    )
    return {
        "run_id": result["run_id"],
        "performance_results": result["performance_results"],
        "performance_result_path": result["performance_result_path"],
        "performance_artifacts": result["performance_artifacts"],
        "agent_logs": [*state.get("agent_logs", []), result["agent_output"]],
        "errors": [*state.get("errors", []), *result.get("errors", [])],
    }


def load_test_plan_file(path: str | Path) -> dict[str, Any]:
    """Load a test_plan JSON file."""

    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_test_plan_from_run_dir(run_dir: str | Path) -> dict[str, Any]:
    """Load test_plan.json from a previous run directory."""

    return load_test_plan_file(Path(run_dir) / "test_plan.json")


def load_discovered_endpoints_from_run_dir(run_dir: str | Path) -> list[dict[str, Any]]:
    """Load discovered_endpoints from workflow_state.json when available."""

    state_path = Path(run_dir) / "workflow_state.json"
    if not state_path.exists():
        return []
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    endpoints = state.get("discovered_endpoints") or []
    return list(endpoints) if isinstance(endpoints, list) else []


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Performance Testing Agent alone.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-dir", default=None)
    source.add_argument("--test-plan", default=None)
    parser.add_argument("--target-url", default=None)
    parser.add_argument("--allow-external", action="store_true")
    parser.add_argument("--users", type=int, default=None)
    parser.add_argument("--spawn-rate", type=float, default=None)
    parser.add_argument("--duration-seconds", type=int, default=None)
    return parser.parse_args()


def _compact_cli_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": result.get("run_id"),
        "summary": result.get("summary"),
        "performance_result_path": result.get("performance_result_path"),
        "artifact_count": len(result.get("performance_artifacts", [])),
        "errors": result.get("errors", []),
    }


def _cli_preferences(args: argparse.Namespace) -> dict[str, Any]:
    preferences: dict[str, Any] = {
        "allow_external_performance_test": bool(args.allow_external)
    }
    if args.users is not None:
        preferences["performance_users"] = args.users
    if args.spawn_rate is not None:
        preferences["performance_spawn_rate"] = args.spawn_rate
    if args.duration_seconds is not None:
        preferences["performance_duration_seconds"] = args.duration_seconds
    return preferences


def main() -> None:
    """CLI entry point for standalone performance testing."""

    args = _parse_args()
    if args.run_dir:
        test_plan = load_test_plan_from_run_dir(args.run_dir)
        discovered_endpoints = load_discovered_endpoints_from_run_dir(args.run_dir)
        run_id = Path(args.run_dir).name
    else:
        test_plan = load_test_plan_file(args.test_plan)
        discovered_endpoints = []
        parent = Path(args.test_plan).parent
        run_id = parent.name if parent.name else None

    result = run_performance_testing_agent_alone(
        target_url=args.target_url or "",
        test_plan=test_plan,
        run_id=run_id,
        user_preferences=_cli_preferences(args),
        discovered_endpoints=discovered_endpoints,
    )
    print(json.dumps(_compact_cli_result(result), indent=2))


if __name__ == "__main__":
    main()
