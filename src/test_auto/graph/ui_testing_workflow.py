"""Mini LangGraph workflow for the standalone UI Testing Agent."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from test_auto.agents.ui_testing_agent import ui_testing_node
from test_auto.graph.state import TestAutomationState


def build_ui_testing_graph():
    """Build START -> ui_testing -> END."""

    workflow = StateGraph(TestAutomationState)
    workflow.add_node("ui_testing", ui_testing_node)
    workflow.add_edge(START, "ui_testing")
    workflow.add_edge("ui_testing", END)
    return workflow.compile()


def run_ui_testing_workflow(initial_state: TestAutomationState) -> dict:
    """Run the mini UI Testing workflow."""

    graph = build_ui_testing_graph()
    return graph.invoke(initial_state)
