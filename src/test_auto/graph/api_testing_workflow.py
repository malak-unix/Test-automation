"""Standalone LangGraph workflow for the API Testing Agent."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from test_auto.agents.api_testing_agent import api_testing_node
from test_auto.graph.state import TestAutomationState


def build_api_testing_graph():
    """Build START -> api_testing -> END."""

    workflow = StateGraph(TestAutomationState)
    workflow.add_node("api_testing", api_testing_node)
    workflow.add_edge(START, "api_testing")
    workflow.add_edge("api_testing", END)
    return workflow.compile()


def run_api_testing_workflow(initial_state: TestAutomationState) -> dict[str, Any]:
    """Run the standalone API testing workflow."""

    graph = build_api_testing_graph()
    return graph.invoke(initial_state)

