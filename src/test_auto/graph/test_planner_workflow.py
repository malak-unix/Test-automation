"""Standalone LangGraph workflow for the Test Planner Agent."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from test_auto.agents.test_planner import test_planner_node
from test_auto.graph.state import TestAutomationState


def build_test_planner_graph():
    """Build START -> test_planner -> END."""

    workflow = StateGraph(TestAutomationState)
    workflow.add_node("test_planner", test_planner_node)
    workflow.add_edge(START, "test_planner")
    workflow.add_edge("test_planner", END)
    return workflow.compile()


def run_test_planner_workflow(initial_state: TestAutomationState) -> dict[str, Any]:
    """Run the standalone Test Planner workflow."""

    graph = build_test_planner_graph()
    return graph.invoke(initial_state)

