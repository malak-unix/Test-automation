"""UI Testing Agent.

Role in the architecture: execute planned UI test cases with Selenium, record
structured outcomes, and capture screenshot paths on failure. It does not start
the target app, authenticate automatically, or generate selectors.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from test_auto.graph.state import TestAutomationState
from test_auto.shared.schemas import UITestingOutput, UISummary, UITestExecutionResult
from test_auto.shared.utils import current_timestamp, generate_run_id
from test_auto.tools.bug_tools import mask_sensitive_values
from test_auto.tools.selenium_tools import (
    compute_ui_summary,
    execute_ui_test_case,
    save_ui_result,
)


UI_TESTING_AGENT_SYSTEM_PROMPT = """
You are the UI Testing Agent.
Execute only UI test cases from the test_plan using Selenium tools.
Prefer stable checks such as page load, visible text, form presence, and login form presence.
Do not invent selectors.
Do not silently ignore failures.
Capture screenshots on failure.
Classify unreachable target or missing browser as environment_error.
Return structured JSON.
"""


def extract_ui_tests(test_plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return UI test case plans from a structured test_plan."""

    ui_tests = (test_plan or {}).get("ui_tests") or []
    return list(ui_tests) if isinstance(ui_tests, list) else []


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text.lower() for token in tokens)


def normalize_ui_test_case(test_case: dict[str, Any]) -> dict[str, Any]:
    """Fill required UI test execution fields without inventing selectors."""

    normalized = dict(test_case or {})
    name = str(normalized.get("name") or "unnamed_ui_test")
    flow = str(normalized.get("flow") or name)
    expected_result = str(normalized.get("expected_result") or "")
    normalized["id"] = str(normalized.get("id") or "UI_UNKNOWN")
    normalized["name"] = name
    normalized["flow"] = flow
    normalized["steps"] = list(normalized.get("steps") or [])
    normalized["expected_result"] = expected_result
    normalized["assertions"] = list(normalized.get("assertions") or [])

    if normalized["assertions"]:
        return normalized

    searchable = f"{name} {flow} {expected_result}".lower()
    if _contains_any(searchable, ("login", "sign in", "signin")):
        normalized["assertions"].append(
            {
                "type": "login_form_present",
                "expected": "login form",
            }
        )
    elif _contains_any(searchable, ("register", "signup", "sign up")):
        normalized["assertions"].append(
            {
                "type": "form_present",
                "expected": "registration form",
            }
        )
    elif expected_result.strip():
        normalized["assertions"].append(
            {
                "type": "page_contains",
                "expected": expected_result,
            }
        )
    else:
        normalized["assertions"].append(
            {
                "type": "ui_visible",
                "expected": name.replace("_", " "),
            }
        )
    return normalized


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
    screenshots: list[dict[str, Any]] | None = None,
    anomalies: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> UITestingOutput:
    return UITestingOutput(
        timestamp=current_timestamp(),
        status=status,
        duration_seconds=duration_seconds,
        summary=UISummary(**summary),
        tests=[UITestExecutionResult(**item) for item in tests],
        screenshots=screenshots or [],
        anomalies=anomalies or [],
        metadata=metadata or {},
    )


def run_ui_testing_agent_alone(
    target_url: str,
    test_plan: dict[str, Any],
    run_id: str | None = None,
    user_preferences: dict[str, Any] | None = None,
    discovered_ui_flows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute planned UI tests against target_url and save ui_result.json."""

    started = time.perf_counter()
    active_run_id = run_id or generate_run_id()
    preferences = mask_sensitive_values(user_preferences or {})
    if not target_url:
        summary = compute_ui_summary([])
        error = {
            "agent": "ui_testing",
            "field": "target_url",
            "message": "target_url is required for UI testing.",
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
        ui_result_path = save_ui_result(active_run_id, output_data)
        return {
            "run_id": active_run_id,
            "ui_results": output_data,
            "ui_result_path": ui_result_path,
            "screenshots": [],
            "summary": summary,
            "errors": [error],
            "agent_output": output_data,
        }

    ui_tests = [normalize_ui_test_case(item) for item in extract_ui_tests(test_plan)]
    if not ui_tests:
        summary = compute_ui_summary([])
        anomaly = {
            "agent": "ui_testing",
            "message": "No UI tests found in test_plan.",
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
        ui_result_path = save_ui_result(active_run_id, output_data)
        return {
            "run_id": active_run_id,
            "ui_results": output_data,
            "ui_result_path": ui_result_path,
            "screenshots": [],
            "summary": summary,
            "errors": [],
            "agent_output": output_data,
        }

    test_results = [
        execute_ui_test_case(
            target_url=target_url,
            test_case=test_case,
            run_id=active_run_id,
            discovered_ui_flows=discovered_ui_flows or [],
            user_preferences=preferences,
        )
        for test_case in ui_tests
    ]
    screenshots = [
        item["screenshot"]
        for item in test_results
        if isinstance(item.get("screenshot"), dict)
    ]
    summary = compute_ui_summary(test_results)
    output = _build_output(
        status=_output_status(summary, test_results),
        duration_seconds=time.perf_counter() - started,
        summary=summary,
        tests=test_results,
        screenshots=screenshots,
        metadata={
            "target_url": target_url,
            "headless": bool(preferences.get("headless", True)),
            "browser": preferences.get("browser", "chrome"),
            "screenshot_on_failure": preferences.get("screenshot_on_failure", True),
        },
    )
    output_data = output.model_dump(mode="json")
    ui_result_path = save_ui_result(active_run_id, output_data)
    return {
        "run_id": active_run_id,
        "ui_results": output_data,
        "ui_result_path": ui_result_path,
        "screenshots": screenshots,
        "summary": summary,
        "errors": [],
        "agent_output": output_data,
    }


def ui_testing_node(state: TestAutomationState) -> dict[str, Any]:
    """LangGraph node that returns a partial State update for UI testing."""

    active_run_id = state.get("run_id") or generate_run_id()
    result = run_ui_testing_agent_alone(
        target_url=state.get("target_url", ""),
        test_plan=state.get("test_plan") or {},
        run_id=active_run_id,
        user_preferences=state.get("user_preferences") or {},
        discovered_ui_flows=state.get("discovered_ui_flows") or [],
    )
    return {
        "run_id": result["run_id"],
        "ui_results": result["ui_results"],
        "ui_result_path": result["ui_result_path"],
        "screenshots": result["screenshots"],
        "agent_logs": [*state.get("agent_logs", []), result["agent_output"]],
        "errors": [*state.get("errors", []), *result.get("errors", [])],
    }


def load_test_plan_file(path: str | Path) -> dict[str, Any]:
    """Load a test_plan JSON file."""

    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_test_plan_from_run_dir(run_dir: str | Path) -> dict[str, Any]:
    """Load test_plan.json from a previous run directory."""

    return load_test_plan_file(Path(run_dir) / "test_plan.json")


def load_discovered_ui_flows_from_run_dir(run_dir: str | Path) -> list[dict[str, Any]]:
    """Load discovered_ui_flows from workflow_state.json when available."""

    state_path = Path(run_dir) / "workflow_state.json"
    if not state_path.exists():
        return []
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    flows = state.get("discovered_ui_flows") or []
    return list(flows) if isinstance(flows, list) else []


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the UI Testing Agent alone.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-dir", default=None)
    source.add_argument("--test-plan", default=None)
    parser.add_argument("--target-url", default=None)
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def _compact_cli_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": result.get("run_id"),
        "summary": result.get("summary"),
        "ui_result_path": result.get("ui_result_path"),
        "screenshot_count": len(result.get("screenshots", [])),
        "errors": result.get("errors", []),
    }


def main() -> None:
    """CLI entry point for standalone UI testing."""

    args = _parse_args()
    if args.run_dir:
        test_plan = load_test_plan_from_run_dir(args.run_dir)
        discovered_ui_flows = load_discovered_ui_flows_from_run_dir(args.run_dir)
        run_id = Path(args.run_dir).name
    else:
        test_plan = load_test_plan_file(args.test_plan)
        discovered_ui_flows = []
        parent = Path(args.test_plan).parent
        run_id = parent.name if parent.name else None

    result = run_ui_testing_agent_alone(
        target_url=args.target_url or "",
        test_plan=test_plan,
        run_id=run_id,
        user_preferences={"headless": not args.headed},
        discovered_ui_flows=discovered_ui_flows,
    )
    print(json.dumps(_compact_cli_result(result), indent=2))


if __name__ == "__main__":
    main()
