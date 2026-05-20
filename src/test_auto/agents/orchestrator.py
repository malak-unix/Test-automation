"""Deterministic Orchestrator Agent.

Role in the architecture: validate the user request, normalize requested test
types, and choose the ordered agent list for the main LangGraph workflow. This
agent does not inspect repository files or execute tests.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from test_auto.agents.base import create_error_output, save_agent_output
from test_auto.graph.state import TestAutomationState
from test_auto.shared.schemas import AgentOutput, AgentSummary, OrchestratorDecision
from test_auto.shared.utils import current_timestamp, generate_run_id, validate_url
from test_auto.tools.repo_tools import is_probably_git_url


SUPPORTED_TEST_TYPES = {"api", "ui", "performance"}
FUTURE_PREFIX_AGENTS = ["repository_analyzer", "rag", "test_planner"]
FUTURE_SUFFIX_AGENTS = ["bug", "report"]


def normalize_test_types(raw_test_types: Any) -> list[str]:
    """Normalize requested test types, defaulting to API testing."""

    if raw_test_types is None or raw_test_types == "":
        return ["api"]
    if isinstance(raw_test_types, str):
        raw_items = [raw_test_types]
    else:
        raw_items = list(raw_test_types)

    normalized: list[str] = []
    for item in raw_items:
        value = str(item).strip().lower()
        if value in SUPPORTED_TEST_TYPES and value not in normalized:
            normalized.append(value)

    return normalized or ["api"]


def build_selected_agents(test_types: list[str]) -> list[str]:
    """Build the future pipeline agent list selected by the orchestrator."""

    selected = [*FUTURE_PREFIX_AGENTS]
    for test_type in test_types:
        if test_type not in selected:
            selected.append(test_type)
    selected.extend(FUTURE_SUFFIX_AGENTS)
    return selected


def build_orchestrator_decision(state: TestAutomationState) -> OrchestratorDecision:
    """Create the deterministic routing decision for a workflow run."""

    user_preferences = state.get("user_preferences") or {}
    run_id = state.get("run_id") or generate_run_id()
    test_types = normalize_test_types(user_preferences.get("test_types"))
    if user_preferences.get("skip_api_testing"):
        test_types = [test_type for test_type in test_types if test_type != "api"]
    selected_agents = build_selected_agents(test_types)

    risks: list[str] = []
    if user_preferences.get("skip_api_testing"):
        risks.append("API testing was explicitly skipped for this run.")
    execution_mode = str(
        user_preferences.get("execution_mode") or "sequential"
    ).strip().lower()
    if execution_mode not in {"sequential", "parallel"}:
        risks.append(
            f"Invalid execution_mode '{execution_mode}' was replaced by 'sequential'."
        )
        execution_mode = "sequential"

    raw_test_types = user_preferences.get("test_types")
    if raw_test_types:
        raw_items = [raw_test_types] if isinstance(raw_test_types, str) else raw_test_types
        unsupported = sorted(
            {
                str(item).strip().lower()
                for item in raw_items
                if str(item).strip().lower() not in SUPPORTED_TEST_TYPES
            }
        )
        if unsupported:
            risks.append(
                "Unsupported test types were ignored: " + ", ".join(unsupported)
            )

    return OrchestratorDecision(
        run_id=run_id,
        selected_agents=selected_agents,
        execution_mode=execution_mode,
        reasoning_summary=(
            "Selected future agents from requested test types using deterministic "
            "milestone-1 rules. No testing agent was executed."
        ),
        risks=risks,
        next_node=selected_agents[0],
    )


def _request_validation_errors(state: TestAutomationState) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    repo_url = state.get("repo_url", "")
    repo_path = state.get("repo_path", "")
    target_url = state.get("target_url", "")
    has_local_repo_path = bool(repo_path) and Path(repo_path).expanduser().resolve().is_dir()
    has_valid_repo_url = validate_url(repo_url) or is_probably_git_url(repo_url)

    if not has_valid_repo_url and not has_local_repo_path:
        errors.append(
            {
                "agent": "orchestrator",
                "field": "repo_url",
                "message": "repo_url is missing or invalid, and no valid local repo_path was provided.",
            }
        )
    if not validate_url(target_url):
        errors.append(
            {
                "agent": "orchestrator",
                "field": "target_url",
                "message": "target_url is missing or is not a valid HTTP(S) URL.",
            }
        )
    return errors


def orchestrator_node(state: TestAutomationState) -> dict[str, Any]:
    """LangGraph node that validates the request and saves a JSON result."""

    started = time.perf_counter()
    try:
        decision = build_orchestrator_decision(state)
        existing_errors = list(state.get("errors", []))
        errors = [*existing_errors, *_request_validation_errors(state)]
        status = "error" if errors else "success"

        output = AgentOutput(
            agent="orchestrator",
            timestamp=current_timestamp(),
            status=status,
            duration_seconds=time.perf_counter() - started,
            summary=AgentSummary(),
            tests=[],
            anomalies=errors,
            metadata={
                "decision": decision.model_dump(mode="json"),
                "request": {
                    "repo_url": state.get("repo_url", ""),
                    "repo_path": state.get("repo_path", ""),
                    "target_url": state.get("target_url", ""),
                    "user_preferences": state.get("user_preferences", {}),
                },
            },
        )
        save_agent_output(output, decision.run_id)

        return {
            "run_id": decision.run_id,
            "selected_agents": decision.selected_agents,
            "orchestrator_decision": decision.model_dump(mode="json"),
            "agent_logs": [*state.get("agent_logs", []), output.model_dump(mode="json")],
            "errors": errors,
        }
    except Exception as error:
        run_id = state.get("run_id") or generate_run_id()
        output = create_error_output("orchestrator", error)
        save_agent_output(output, run_id)
        return {
            "run_id": run_id,
            "selected_agents": [],
            "orchestrator_decision": {},
            "agent_logs": [*state.get("agent_logs", []), output.model_dump(mode="json")],
            "errors": [
                *state.get("errors", []),
                {
                    "agent": "orchestrator",
                    "field": "internal",
                    "message": str(error),
                },
            ],
        }


def run_orchestrator_alone(
    repo_url: str,
    target_url: str,
    user_preferences: dict[str, Any],
) -> dict[str, Any]:
    """Run the Orchestrator Agent without the LangGraph workflow."""

    state: TestAutomationState = {
        "run_id": "",
        "repo_url": repo_url,
        "target_url": target_url,
        "user_preferences": user_preferences,
        "selected_agents": [],
        "orchestrator_decision": {},
        "errors": [],
        "agent_logs": [],
    }
    return orchestrator_node(state)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Orchestrator Agent alone.")
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--test-types", nargs="+", default=None)
    parser.add_argument("--execution-mode", default="sequential")
    parser.add_argument("--max-duration-minutes", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    """CLI entry point for the standalone Orchestrator Agent."""

    args = _parse_args()
    result = run_orchestrator_alone(
        repo_url=args.repo_url,
        target_url=args.target_url,
        user_preferences={
            "test_types": args.test_types,
            "execution_mode": args.execution_mode,
            "max_duration_minutes": args.max_duration_minutes,
        },
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
