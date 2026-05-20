"""Standalone LangGraph workflow for the Repository Analyzer Agent."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from test_auto.agents.repo_analyzer import repo_analyzer_node
from test_auto.graph.state import TestAutomationState


def build_repo_analyzer_graph():
    """Build START -> repo_analyzer -> END."""

    workflow = StateGraph(TestAutomationState)
    workflow.add_node("repo_analyzer", repo_analyzer_node)
    workflow.add_edge(START, "repo_analyzer")
    workflow.add_edge("repo_analyzer", END)
    return workflow.compile()


def run_repo_analyzer_workflow(initial_state: TestAutomationState) -> dict[str, Any]:
    """Run the standalone Repository Analyzer graph."""

    graph = build_repo_analyzer_graph()
    return graph.invoke(initial_state)
