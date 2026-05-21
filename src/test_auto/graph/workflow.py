"""Main LangGraph workflow for the progressive test automation project.

Architecture in one place:
- Orchestrator validates input and decides which agents are selected.
- Repository Analyzer safely reads or clones the repository; it never runs it.
- RAG builds local context from selected files for grounded planning.
- Test Planner creates API/UI/performance test cases from repository evidence.
- API, UI, and Performance agents execute only planned safe checks.
- Bug Analysis classifies anomalies from execution results.
- Report aggregates everything into final JSON and HTML dashboard artifacts.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pathlib import Path

from langgraph.graph import END, START, StateGraph

from test_auto.agents.api_testing_agent import api_testing_node
from test_auto.agents.bug_analysis_agent import bug_analysis_node
from test_auto.agents.orchestrator import orchestrator_node
from test_auto.agents.performance_testing_agent import performance_testing_node
from test_auto.agents.rag_agent import rag_node
from test_auto.agents.report_agent import report_node
from test_auto.agents.repo_analyzer import repo_analyzer_node
from test_auto.agents.test_planner import test_planner_node
from test_auto.agents.ui_testing_agent import ui_testing_node
from test_auto.graph.routing import (
    route_after_api_testing,
    route_after_bug_analysis,
    route_after_orchestrator,
    route_after_performance_testing,
    route_after_rag,
    route_after_repo_analyzer,
    route_after_test_planner,
    route_after_ui_testing,
)
from test_auto.graph.state import TestAutomationState
from test_auto.shared.utils import generate_run_id, save_workflow_state


ProgressCallback = Callable[[dict[str, Any]], None]


def _node_status_from_update(update: dict[str, Any]) -> str:
    logs = update.get("agent_logs") or []
    if logs and isinstance(logs[-1], dict):
        return str(logs[-1].get("status") or "success")
    if update.get("errors"):
        return "partial"
    return "success"


def _wrap_node(
    name: str,
    node_func: Callable[[TestAutomationState], dict[str, Any]],
    progress_callback: ProgressCallback | None,
) -> Callable[[TestAutomationState], dict[str, Any]]:
    if progress_callback is None:
        return node_func

    def wrapped(state: TestAutomationState) -> dict[str, Any]:
        progress_callback(
            {
                "agent": name,
                "status": "running",
                "message": f"{name} started.",
            }
        )
        try:
            update = node_func(state)
        except Exception as error:
            progress_callback(
                {
                    "agent": name,
                    "status": "error",
                    "message": f"{name} failed: {error.__class__.__name__}",
                }
            )
            raise
        progress_callback(
            {
                "agent": name,
                "status": _node_status_from_update(update),
                "message": f"{name} completed.",
            }
        )
        return update

    return wrapped


def build_graph(progress_callback: ProgressCallback | None = None):
    """Build the full integrated workflow through Report Agent."""

    workflow = StateGraph(TestAutomationState)

    # Each node is one agent. Nodes communicate only through TestAutomationState,
    # so every agent stays testable alone and in the integrated workflow.
    workflow.add_node("orchestrator", _wrap_node("orchestrator", orchestrator_node, progress_callback))
    workflow.add_node("repo_analyzer", _wrap_node("repo_analyzer", repo_analyzer_node, progress_callback))
    workflow.add_node("rag", _wrap_node("rag", rag_node, progress_callback))
    workflow.add_node("test_planner", _wrap_node("test_planner", test_planner_node, progress_callback))
    workflow.add_node("api_testing", _wrap_node("api_testing", api_testing_node, progress_callback))
    workflow.add_node("ui_testing", _wrap_node("ui_testing", ui_testing_node, progress_callback))
    workflow.add_node(
        "performance_testing",
        _wrap_node("performance_testing", performance_testing_node, progress_callback),
    )
    workflow.add_node("bug_analysis", _wrap_node("bug_analysis", bug_analysis_node, progress_callback))
    workflow.add_node("report", _wrap_node("report", report_node, progress_callback))

    # The normal happy path is:
    # START -> orchestrator -> repo_analyzer -> rag -> test_planner
    # -> api_testing -> ui_testing -> performance_testing -> bug_analysis
    # -> report -> END.
    # Conditional edges below keep the workflow safe when inputs are missing,
    # a user skips an agent, or a previous agent cannot produce usable data.
    workflow.add_edge(START, "orchestrator")
    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "repo_analyzer": "repo_analyzer",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "repo_analyzer",
        route_after_repo_analyzer,
        {
            "rag": "rag",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "rag",
        route_after_rag,
        {
            "test_planner": "test_planner",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "test_planner",
        route_after_test_planner,
        {
            "api_testing": "api_testing",
            "ui_testing": "ui_testing",
            "performance_testing": "performance_testing",
            "bug_analysis": "bug_analysis",
            "report": "report",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "api_testing",
        route_after_api_testing,
        {
            "ui_testing": "ui_testing",
            "performance_testing": "performance_testing",
            "bug_analysis": "bug_analysis",
            "report": "report",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "ui_testing",
        route_after_ui_testing,
        {
            "performance_testing": "performance_testing",
            "bug_analysis": "bug_analysis",
            "report": "report",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "performance_testing",
        route_after_performance_testing,
        {
            "bug_analysis": "bug_analysis",
            "report": "report",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "bug_analysis",
        route_after_bug_analysis,
        {
            "report": "report",
            "end": END,
        },
    )
    workflow.add_edge("report", END)
    return workflow.compile()


def run_workflow(
    initial_state: TestAutomationState,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run the integrated workflow and save final State."""

    graph = build_graph(progress_callback=progress_callback)
    final_state = graph.invoke(initial_state)
    run_id = final_state.get("run_id") or generate_run_id()
    final_state["run_id"] = run_id
    run_dir = Path("results") / "runs" / run_id
    # Save only artifact paths in State. Large files, screenshots, and reports
    # stay on disk under results/runs/<run_id>/ or reports/generated/.
    candidates = {
        "orchestrator_result": run_dir / "orchestrator_result.json",
        "repo_analyzer_result": run_dir / "repo_analyzer_result.json",
        "project_info": run_dir / "project_info.json",
        "rag_result": run_dir / "rag_result.json",
        "retrieved_context": run_dir / "retrieved_context.json",
        "rag_index_manifest": run_dir / "rag_index" / "manifest.json",
        "test_plan": run_dir / "test_plan.json",
        "test_planner_result": run_dir / "test_planner_result.json",
        "api_result": run_dir / "api_result.json",
        "ui_result": run_dir / "ui_result.json",
        "performance_result": run_dir / "performance_result.json",
        "bug_result": run_dir / "bug_result.json",
        "final_results": run_dir / "final_results.json",
        "report_result": run_dir / "report_result.json",
    }
    output_files = {
        name: str(path)
        for name, path in candidates.items()
        if path.exists()
    }
    if final_state.get("report_html_path"):
        output_files["report_html"] = final_state["report_html_path"]
    output_files["workflow_state"] = str(run_dir / "workflow_state.json")
    final_state["output_files"] = output_files
    final_state["workflow_state_path"] = output_files["workflow_state"]
    save_workflow_state(final_state, run_id)
    return final_state
