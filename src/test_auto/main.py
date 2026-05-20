"""Main CLI entry point for the integrated LangGraph workflow."""

from __future__ import annotations

import argparse
import json

from test_auto.graph.state import TestAutomationState
from test_auto.graph.workflow import run_workflow


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the integrated test automation graph.")
    parser.add_argument("--repo-url", default=None)
    parser.add_argument("--repo-path", default=None)
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--test-types", nargs="+", default=None)
    parser.add_argument("--execution-mode", default="sequential")
    parser.add_argument("--max-duration-minutes", type=int, default=5)
    parser.add_argument("--focus", default=None)
    parser.add_argument("--rag-query", default=None)
    parser.add_argument("--rag-top-k", type=int, default=None)
    planner_mode = parser.add_mutually_exclusive_group()
    planner_mode.add_argument("--planner-no-llm", action="store_true", help=argparse.SUPPRESS)
    planner_mode.add_argument("--planner-use-llm", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--allow-mutating-api-tests", action="store_true")
    parser.add_argument("--skip-api-testing", action="store_true")
    parser.add_argument("--skip-ui-testing", action="store_true")
    parser.add_argument("--skip-performance-testing", action="store_true")
    parser.add_argument("--allow-external-performance-test", action="store_true")
    parser.add_argument("--skip-bug-analysis", action="store_true")
    parser.add_argument("--skip-report", action="store_true")
    parser.add_argument("--use-mcp-tools", action="store_true")
    return parser.parse_args()


def _tool_backend_summary(final_state: dict) -> dict:
    summary: dict[str, dict] = {}
    for log in final_state.get("agent_logs", []) or []:
        if not isinstance(log, dict):
            continue
        agent = log.get("agent")
        metadata = log.get("metadata") or {}
        if agent and (
            "tool_backend" in metadata
            or "mcp_fallback_used" in metadata
        ):
            summary[str(agent)] = {
                "tool_backend": metadata.get("tool_backend", "local"),
                "mcp_fallback_used": bool(metadata.get("mcp_fallback_used", False)),
            }
    return summary


def _compact_final_state(final_state: dict) -> dict:
    """Return a terminal-friendly final State summary."""

    project_info = final_state.get("project_info") or {}
    test_plan = final_state.get("test_plan") or {}
    planner_model_info = final_state.get("planner_model_info") or {}
    api_results = final_state.get("api_results") or {}
    api_summary = api_results.get("summary") or {}
    ui_results = final_state.get("ui_results") or {}
    ui_summary = ui_results.get("summary") or {}
    performance_results = final_state.get("performance_results") or {}
    performance_summary = performance_results.get("summary") or {}
    bug_results = final_state.get("bug_results") or {}
    bug_summary = bug_results.get("summary") or {}
    final_results = final_state.get("final_results") or {}
    report_kpis = final_results.get("kpis") or {}
    dashboard_payload = final_state.get("dashboard_payload") or {}
    user_preferences = final_state.get("user_preferences") or {}
    tool_metadata = _tool_backend_summary(final_state)
    return {
        "run_id": final_state.get("run_id"),
        "selected_agents": final_state.get("selected_agents", []),
        "use_mcp_tools": bool(user_preferences.get("use_mcp_tools", False)),
        "mcp_fallback_used": any(
            item.get("mcp_fallback_used") for item in tool_metadata.values()
        ),
        "tool_backend_metadata": tool_metadata,
        "project_info_framework": project_info.get("framework"),
        "discovered_endpoints_count": len(final_state.get("discovered_endpoints", [])),
        "indexed_documents_count": len(final_state.get("indexed_documents", [])),
        "rag_query": final_state.get("rag_query"),
        "retrieved_context_count": len(final_state.get("retrieved_context", [])),
        "test_plan_path": final_state.get("test_plan_path"),
        "test_planner_result_path": final_state.get("test_planner_result_path"),
        "api_result_path": final_state.get("api_result_path"),
        "ui_result_path": final_state.get("ui_result_path"),
        "performance_result_path": final_state.get("performance_result_path"),
        "performance_artifact_count": len(final_state.get("performance_artifacts", []) or []),
        "bug_result_path": final_state.get("bug_result_path"),
        "final_results_path": final_state.get("final_results_path"),
        "report_result_path": final_state.get("report_result_path"),
        "report_html_path": final_state.get("report_html_path"),
        "planner_model_mode": planner_model_info.get("mode"),
        "api_tests_count": len(test_plan.get("api_tests", [])),
        "ui_tests_count": len(test_plan.get("ui_tests", [])),
        "performance_tests_count": len(test_plan.get("performance_tests", [])),
        "api_summary": {
            "total_tests": api_summary.get("total_tests", 0),
            "passed": api_summary.get("passed", 0),
            "failed": api_summary.get("failed", 0),
            "skipped": api_summary.get("skipped", 0),
            "errors": api_summary.get("errors", 0),
            "pass_rate": api_summary.get("pass_rate", 0.0),
        },
        "ui_summary": {
            "total_tests": ui_summary.get("total_tests", 0),
            "passed": ui_summary.get("passed", 0),
            "failed": ui_summary.get("failed", 0),
            "skipped": ui_summary.get("skipped", 0),
            "errors": ui_summary.get("errors", 0),
            "pass_rate": ui_summary.get("pass_rate", 0.0),
        },
        "performance_summary": {
            "total_tests": performance_summary.get("total_tests", 0),
            "passed": performance_summary.get("passed", 0),
            "failed": performance_summary.get("failed", 0),
            "skipped": performance_summary.get("skipped", 0),
            "errors": performance_summary.get("errors", 0),
            "average_response_time_ms": performance_summary.get("average_response_time_ms"),
            "p95_response_time_ms": performance_summary.get("p95_response_time_ms"),
            "overall_failure_rate": performance_summary.get("overall_failure_rate", 0.0),
        },
        "screenshot_count": len(final_state.get("screenshots", []) or []),
        "bug_summary": {
            "total_anomalies": bug_summary.get("total_anomalies", 0),
            "high": bug_summary.get("high", 0),
            "medium": bug_summary.get("medium", 0),
            "low": bug_summary.get("low", 0),
            "info": bug_summary.get("info", 0),
        },
        "report_kpis": {
            "global_score": report_kpis.get("global_score", 0.0),
            "recommendation_count": report_kpis.get("recommendation_count", 0),
        },
        "dashboard_payload_summary": {
            "run_id": dashboard_payload.get("run_id"),
            "global_score": dashboard_payload.get("global_score"),
            "status": dashboard_payload.get("status"),
            "report_html_path": dashboard_payload.get("report_html_path"),
        },
        "recommendations_count": len(final_state.get("recommendations", [])),
        "missing_information": (
            test_plan.get("missing_information")
            or final_state.get("missing_information", [])
        ),
        "output_files": final_state.get("output_files", {}),
        "workflow_state_path": final_state.get("workflow_state_path"),
        "errors": final_state.get("errors", []),
    }


def main() -> None:
    """Parse CLI input, run the graph, and print JSON state."""

    args = _parse_args()
    user_preferences = {
        "test_types": args.test_types,
        "execution_mode": args.execution_mode,
        "max_duration_minutes": args.max_duration_minutes,
    }
    if args.focus:
        user_preferences["focus"] = args.focus
    if args.rag_query:
        user_preferences["rag_query"] = args.rag_query
    if args.rag_top_k is not None:
        user_preferences["rag_top_k"] = args.rag_top_k
    # CLI runs are LLM-first. --planner-no-llm remains only as an emergency
    # offline/testing escape hatch; normal project usage calls Groq/Mistral.
    user_preferences["planner_use_llm"] = not bool(args.planner_no_llm)
    user_preferences["allow_mutating_api_tests"] = bool(args.allow_mutating_api_tests)
    user_preferences["skip_api_testing"] = bool(args.skip_api_testing)
    user_preferences["skip_ui_testing"] = bool(args.skip_ui_testing)
    user_preferences["skip_performance_testing"] = bool(args.skip_performance_testing)
    user_preferences["allow_external_performance_test"] = bool(
        args.allow_external_performance_test
    )
    user_preferences["skip_bug_analysis"] = bool(args.skip_bug_analysis)
    user_preferences["skip_report"] = bool(args.skip_report)
    user_preferences["use_mcp_tools"] = bool(args.use_mcp_tools)

    initial_state: TestAutomationState = {
        "run_id": "",
        "repo_url": args.repo_url or "",
        "repo_path": args.repo_path or "",
        "target_url": args.target_url,
        "user_preferences": user_preferences,
        "selected_agents": [],
        "orchestrator_decision": {},
        "errors": [],
        "agent_logs": [],
    }
    final_state = run_workflow(initial_state)
    print(json.dumps(_compact_final_state(final_state), indent=2))


if __name__ == "__main__":
    main()
