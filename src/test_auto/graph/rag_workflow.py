"""Standalone LangGraph workflow for the RAG Knowledge Agent."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from test_auto.agents.rag_agent import rag_node
from test_auto.graph.state import TestAutomationState


def build_rag_graph():
    """Build START -> rag -> END."""

    workflow = StateGraph(TestAutomationState)
    workflow.add_node("rag", rag_node)
    workflow.add_edge(START, "rag")
    workflow.add_edge("rag", END)
    return workflow.compile()


def run_rag_workflow(initial_state: TestAutomationState) -> dict[str, Any]:
    """Run the standalone RAG workflow."""

    graph = build_rag_graph()
    return graph.invoke(initial_state)
