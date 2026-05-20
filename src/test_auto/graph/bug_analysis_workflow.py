"""Standalone LangGraph workflow for the Bug Analysis Agent."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from test_auto.agents.bug_analysis_agent import bug_analysis_node
from test_auto.graph.state import TestAutomationState


def build_bug_analysis_graph():
    """Build START -> bug_analysis -> END."""

    workflow = StateGraph(TestAutomationState)
    workflow.add_node("bug_analysis", bug_analysis_node)
    workflow.add_edge(START, "bug_analysis")
    workflow.add_edge("bug_analysis", END)
    return workflow.compile()


def run_bug_analysis_workflow(initial_state: TestAutomationState) -> dict[str, Any]:
    """Run the standalone Bug Analysis mini workflow."""

    graph = build_bug_analysis_graph()
    return graph.invoke(initial_state)
