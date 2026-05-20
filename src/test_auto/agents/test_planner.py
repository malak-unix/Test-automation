"""Test Planner Agent.

Role in the architecture: call the configured Groq/Mistral planner to turn
project metadata, discovered routes, retrieved RAG context, and user
preferences into grounded API/UI/performance test cases. Deterministic planning
exists only as a safe fallback if the LLM call fails.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from test_auto.agents.base import create_error_output, save_agent_output
from test_auto.graph.state import TestAutomationState
from test_auto.planning.prompt_builder import TEST_PLANNER_SYSTEM_PROMPT
from test_auto.planning.validators import (
    repair_or_filter_invalid_test_plan,
    validate_test_plan_against_evidence,
)
from test_auto.shared.schemas import TestPlan, TestPlannerOutput
from test_auto.shared.utils import current_timestamp, generate_run_id
from test_auto.tools.planning_tools import (
    build_planner_context_from_state,
    generate_test_plan_from_context,
    persist_test_planner_outputs,
)


def _empty_error_plan(message: str) -> dict[str, Any]:
    return TestPlan(
        scope="Unable to create a grounded test plan",
        assumptions=[],
        api_tests=[],
        ui_tests=[],
        performance_tests=[],
        excluded_tests=[],
        missing_information=[message],
        risks=[],
        reasoning_summary="Planning could not proceed because required evidence was missing.",
    ).model_dump(mode="json")


def run_test_planner_alone(
    project_info: dict[str, Any] | None = None,
    discovered_endpoints: list[dict[str, Any]] | None = None,
    discovered_ui_flows: list[dict[str, Any]] | None = None,
    retrieved_context: list[dict[str, Any]] | None = None,
    user_preferences: dict[str, Any] | None = None,
    missing_information: list[str] | None = None,
    run_id: str | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Generate a grounded test plan and save planner artifacts."""

    started = time.perf_counter()
    active_run_id = run_id or generate_run_id()
    context = build_planner_context_from_state(
        {
            "project_info": project_info or {},
            "discovered_endpoints": discovered_endpoints or [],
            "discovered_ui_flows": discovered_ui_flows or [],
            "retrieved_context": retrieved_context or [],
            "user_preferences": user_preferences or {},
            "missing_information": missing_information or [],
        }
    )

    try:
        test_plan, model_info = generate_test_plan_from_context(context, use_llm=use_llm)
        validation = validate_test_plan_against_evidence(
            test_plan,
            context["discovered_endpoints"],
            context["retrieved_context"],
        )
        if not validation["is_valid"]:
            test_plan = repair_or_filter_invalid_test_plan(
                test_plan,
                context["discovered_endpoints"],
                context["retrieved_context"],
            )
            validation = validate_test_plan_against_evidence(
                test_plan,
                context["discovered_endpoints"],
                context["retrieved_context"],
            )

        status = "success" if validation["is_valid"] else "partial"
        if test_plan.get("missing_information"):
            status = "partial"
        output = TestPlannerOutput(
            timestamp=current_timestamp(),
            status=status,
            duration_seconds=time.perf_counter() - started,
            test_plan=TestPlan(**test_plan),
            model_info=model_info,
            anomalies=[
                {"type": "validation_issue", "message": issue}
                for issue in validation["issues"]
            ],
            metadata={
                "prompt_structure": "system_message + few_shot_example + user_input",
                "use_llm_requested": use_llm,
            },
        )
        paths = persist_test_planner_outputs(
            active_run_id,
            test_plan,
            output.model_dump(mode="json"),
        )
        return {
            "run_id": active_run_id,
            "test_plan": test_plan,
            "test_plan_path": paths["test_plan_path"],
            "test_planner_result_path": paths["test_planner_result_path"],
            "planner_model_info": model_info,
            "validation": validation,
            "agent_output": output.model_dump(mode="json"),
            "errors": [],
        }
    except Exception as error:
        message = str(error)
        test_plan = _empty_error_plan(message)
        output = TestPlannerOutput(
            timestamp=current_timestamp(),
            status="error",
            duration_seconds=time.perf_counter() - started,
            test_plan=TestPlan(**test_plan),
            model_info={
                "mode": "deterministic_fallback",
                "provider": "none",
                "model": None,
                "reason": "Planner failed before producing a valid plan.",
            },
            anomalies=[{"agent": "test_planner", "field": "internal", "message": message}],
            metadata={"use_llm_requested": use_llm},
        )
        paths = persist_test_planner_outputs(
            active_run_id,
            test_plan,
            output.model_dump(mode="json"),
        )
        return {
            "run_id": active_run_id,
            "test_plan": test_plan,
            "test_plan_path": paths["test_plan_path"],
            "test_planner_result_path": paths["test_planner_result_path"],
            "planner_model_info": output.model_info,
            "validation": {"is_valid": False, "issues": [message]},
            "agent_output": output.model_dump(mode="json"),
            "errors": [{"agent": "test_planner", "field": "internal", "message": message}],
        }


def test_planner_node(state: TestAutomationState) -> dict[str, Any]:
    """LangGraph node that returns a partial State update for planning."""

    active_run_id = state.get("run_id") or generate_run_id()
    try:
        result = run_test_planner_alone(
            project_info=state.get("project_info"),
            discovered_endpoints=state.get("discovered_endpoints"),
            discovered_ui_flows=state.get("discovered_ui_flows"),
            retrieved_context=state.get("retrieved_context"),
            user_preferences=state.get("user_preferences"),
            missing_information=state.get("missing_information"),
            run_id=active_run_id,
            use_llm=bool(
                (state.get("user_preferences") or {}).get("planner_use_llm", False)
            ),
        )
        return {
            "run_id": result["run_id"],
            "test_plan": result["test_plan"],
            "test_plan_path": result["test_plan_path"],
            "test_planner_result_path": result["test_planner_result_path"],
            "planner_model_info": result["planner_model_info"],
            "agent_logs": [*state.get("agent_logs", []), result["agent_output"]],
            "errors": [*state.get("errors", []), *result.get("errors", [])],
        }
    except Exception as error:
        output = create_error_output("test_planner", error, metadata={})
        path = save_agent_output(output, active_run_id)
        return {
            "run_id": active_run_id,
            "test_plan": _empty_error_plan(str(error)),
            "test_plan_path": "",
            "test_planner_result_path": path,
            "planner_model_info": {
                "mode": "deterministic_fallback",
                "provider": "none",
                "reason": "Planner node exception.",
            },
            "agent_logs": [*state.get("agent_logs", []), output.model_dump(mode="json")],
            "errors": [
                *state.get("errors", []),
                {"agent": "test_planner", "field": "internal", "message": str(error)},
            ],
        }


def load_planner_context_from_run_dir(run_dir: str | Path) -> dict[str, Any]:
    """Load planner context from previous workflow artifacts."""

    base = Path(run_dir)
    state_path = base / "workflow_state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return build_planner_context_from_state(state)

    context: dict[str, Any] = {
        "project_info": {},
        "discovered_endpoints": [],
        "discovered_ui_flows": [],
        "retrieved_context": [],
        "user_preferences": {},
        "missing_information": [],
    }
    project_info_path = base / "project_info.json"
    if project_info_path.exists():
        context["project_info"] = json.loads(project_info_path.read_text(encoding="utf-8"))
    repo_result_path = base / "repo_analyzer_result.json"
    if repo_result_path.exists():
        repo_result = json.loads(repo_result_path.read_text(encoding="utf-8"))
        context["discovered_endpoints"] = repo_result.get("discovered_endpoints", [])
        context["discovered_ui_flows"] = repo_result.get("discovered_ui_flows", [])
    retrieved_path = base / "retrieved_context.json"
    if retrieved_path.exists():
        context["retrieved_context"] = json.loads(retrieved_path.read_text(encoding="utf-8"))
    return build_planner_context_from_state(context)


def load_planner_context_from_json(path: str | Path) -> dict[str, Any]:
    """Load planner context from a JSON file."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return build_planner_context_from_state(data)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Test Planner Agent alone.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--context-json", default=None)
    source.add_argument("--run-dir", default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--no-llm", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--use-llm", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def _compact_cli_result(result: dict[str, Any]) -> dict[str, Any]:
    plan = result.get("test_plan") or {}
    return {
        "run_id": result.get("run_id"),
        "api_tests_count": len(plan.get("api_tests", [])),
        "ui_tests_count": len(plan.get("ui_tests", [])),
        "performance_tests_count": len(plan.get("performance_tests", [])),
        "missing_information": plan.get("missing_information", []),
        "test_plan_path": result.get("test_plan_path"),
        "test_planner_result_path": result.get("test_planner_result_path"),
        "planner_model_info": result.get("planner_model_info"),
        "validation": result.get("validation"),
        "errors": result.get("errors", []),
    }


def main() -> None:
    """CLI entry point for standalone test planning."""

    args = _parse_args()
    if args.run_dir:
        context = load_planner_context_from_run_dir(args.run_dir)
        run_id = Path(args.run_dir).name
    else:
        context = load_planner_context_from_json(args.context_json)
        run_id = None

    use_llm = not bool(args.no_llm)
    result = run_test_planner_alone(
        project_info=context.get("project_info"),
        discovered_endpoints=context.get("discovered_endpoints"),
        discovered_ui_flows=context.get("discovered_ui_flows"),
        retrieved_context=context.get("retrieved_context"),
        user_preferences=context.get("user_preferences"),
        missing_information=context.get("missing_information"),
        run_id=run_id,
        use_llm=use_llm,
    )
    print(json.dumps(_compact_cli_result(result), indent=2))


if __name__ == "__main__":
    main()
