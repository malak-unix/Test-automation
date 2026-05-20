"""Mini LangGraph workflow for the standalone Performance Testing Agent."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from test_auto.agents.performance_testing_agent import performance_testing_node
from test_auto.graph.state import TestAutomationState


def build_performance_testing_graph():
    """Build START -> performance_testing -> END."""

    workflow = StateGraph(TestAutomationState)
    workflow.add_node("performance_testing", performance_testing_node)
    workflow.add_edge(START, "performance_testing")
    workflow.add_edge("performance_testing", END)
    return workflow.compile()


def run_performance_testing_workflow(
    initial_state: TestAutomationState,
) -> dict[str, Any]:
    """Run the standalone Performance Testing workflow."""

    graph = build_performance_testing_graph()
    return graph.invoke(initial_state)
