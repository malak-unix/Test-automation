"""Standalone LangGraph workflow for the Report Agent."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from test_auto.agents.report_agent import report_node
from test_auto.graph.state import TestAutomationState


def build_report_graph():
    """Build START -> report -> END."""

    workflow = StateGraph(TestAutomationState)
    workflow.add_node("report", report_node)
    workflow.add_edge(START, "report")
    workflow.add_edge("report", END)
    return workflow.compile()


def run_report_workflow(initial_state: TestAutomationState) -> dict[str, Any]:
    """Run the standalone Report mini workflow."""

    graph = build_report_graph()
    return graph.invoke(initial_state)
