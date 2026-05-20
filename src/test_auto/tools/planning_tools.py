"""Local planning tools used by the standalone Test Planner Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from test_auto.planning.deterministic_planner import generate_deterministic_test_plan
from test_auto.planning.llm_planner import plan_with_llm_or_fallback
from test_auto.planning.prompt_builder import compact_context_for_prompt
from test_auto.planning.validators import save_test_plan
from test_auto.shared.utils import ensure_directory, write_json_file


def build_planner_context_from_state(state: dict[str, Any]) -> dict[str, Any]:
    """Extract compact planner context from LangGraph State."""

    context = compact_context_for_prompt(
        project_info=state.get("project_info") or {},
        discovered_endpoints=state.get("discovered_endpoints") or [],
        discovered_ui_flows=state.get("discovered_ui_flows") or [],
        retrieved_context=state.get("retrieved_context") or [],
        user_preferences=state.get("user_preferences") or {},
    )
    context["missing_information"] = state.get("missing_information") or []
    return context


def _fallback_inputs(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_info": context.get("project_info") or {},
        "discovered_endpoints": context.get("discovered_endpoints") or [],
        "discovered_ui_flows": context.get("discovered_ui_flows") or [],
        "retrieved_context": context.get("retrieved_context") or [],
        "user_preferences": context.get("user_preferences") or {},
        "missing_information": context.get("missing_information") or [],
    }


def generate_test_plan_from_context(
    context: dict[str, Any],
    use_llm: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate a test plan from compact context and return model metadata."""

    fallback_inputs = _fallback_inputs(context)
    if not use_llm:
        return (
            generate_deterministic_test_plan(**fallback_inputs),
            {
                "mode": "deterministic_fallback",
                "provider": "none",
                "model": None,
                "reason": "LLM disabled for this run.",
            },
        )
    return plan_with_llm_or_fallback(context, fallback_inputs)


def persist_test_planner_outputs(
    run_id: str,
    test_plan: dict[str, Any],
    planner_output: dict[str, Any],
    results_dir: str = "results",
) -> dict[str, str]:
    """Save test_plan.json and test_planner_result.json for one run."""

    run_dir = ensure_directory(Path(results_dir) / "runs" / run_id)
    test_plan_path = save_test_plan(run_id, test_plan, results_dir)
    result_path = write_json_file(run_dir / "test_planner_result.json", planner_output)
    return {
        "test_plan_path": test_plan_path,
        "test_planner_result_path": str(result_path),
    }

