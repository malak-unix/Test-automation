"""RAG Knowledge Agent.

Role in the architecture: select repository evidence, create deterministic
local chunks/vectors, and retrieve context for the planner. It prepares
grounding data only; it does not generate or execute tests.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from test_auto.agents.base import create_error_output, save_agent_output
from test_auto.agents.repo_analyzer import analyze_repository
from test_auto.graph.state import TestAutomationState
from test_auto.rag.retriever import build_default_rag_query, retrieve_context_for_testing
from test_auto.rag.vector_store import save_retrieved_context
from test_auto.shared.schemas import RAGAgentOutput, RetrievedContext
from test_auto.shared.utils import current_timestamp, ensure_directory, generate_run_id, write_json_file
from test_auto.tools.rag_tools import index_project_documents, select_source_paths_for_rag


RAG_AGENT_SYSTEM_PROMPT = """
You are the RAG Knowledge Agent.
Index relevant project documents and retrieve context for the requested testing scope.
Return file paths, short chunks, relevance scores, and relevance reasons.
Do not generate tests.
Do not infer business rules without retrieved evidence.
If context is weak, explicitly report missing_information.
"""


def build_rag_agent_query(
    project_info: dict[str, Any],
    user_preferences: dict[str, Any] | None = None,
    explicit_query: str | None = None,
) -> str:
    """Build the RAG retrieval query for the current testing scope."""

    if explicit_query:
        return explicit_query
    return build_default_rag_query(project_info, user_preferences)


def _save_rag_output(output: RAGAgentOutput, run_id: str) -> str:
    run_dir = ensure_directory(Path("results") / "runs" / run_id)
    path = run_dir / "rag_result.json"
    write_json_file(path, output.model_dump(mode="json"))
    return str(path)


def _error_result(
    run_id: str,
    error_message: str,
    query: str = "",
    repo_path: str = "",
) -> dict[str, Any]:
    error = {"agent": "rag", "field": "repo_path", "message": error_message}
    output = RAGAgentOutput(
        timestamp=current_timestamp(),
        status="error",
        duration_seconds=0.0,
        query=query,
        index_path=None,
        chunk_count=0,
        retrieved_context=[],
        missing_information=[error_message],
        anomalies=[error],
        metadata={"repo_path": repo_path},
    )
    agent_output_path = _save_rag_output(output, run_id)
    retrieved_context_path = save_retrieved_context(run_id, [])
    return {
        "run_id": run_id,
        "repo_path": repo_path,
        "rag_query": query,
        "rag_index_path": "",
        "chunk_count": 0,
        "retrieved_context": [],
        "missing_information": [error_message],
        "agent_output_path": agent_output_path,
        "retrieved_context_path": retrieved_context_path,
        "errors": [error],
        "agent_output": output.model_dump(mode="json"),
    }


def _prepare_repository_metadata(
    repo_path: str | None,
    repo_url: str | None,
    project_info: dict[str, Any] | None,
    indexed_documents: list[dict[str, Any]] | None,
    run_id: str,
) -> dict[str, Any]:
    if repo_path and project_info is not None and indexed_documents is not None:
        return {
            "repo_path": repo_path,
            "project_info": project_info,
            "indexed_documents": indexed_documents,
            "errors": [],
        }

    if repo_path or repo_url:
        analysis = analyze_repository(repo_url=repo_url, repo_path=repo_path, run_id=run_id)
        return {
            "repo_path": analysis.get("repo_path", repo_path or ""),
            "project_info": project_info or analysis.get("project_info", {}),
            "indexed_documents": indexed_documents or analysis.get("indexed_documents", []),
            "errors": analysis.get("errors", []),
        }

    return {
        "repo_path": "",
        "project_info": project_info or {},
        "indexed_documents": indexed_documents or [],
        "errors": [
            {
                "agent": "rag",
                "field": "repo_path",
                "message": "Provide repo_path or repo_url before running RAG.",
            }
        ],
    }


def run_rag_agent_alone(
    repo_path: str | None = None,
    repo_url: str | None = None,
    project_info: dict[str, Any] | None = None,
    indexed_documents: list[dict[str, Any]] | None = None,
    user_preferences: dict[str, Any] | None = None,
    run_id: str | None = None,
    query: str | None = None,
    top_k: int = 8,
) -> dict[str, Any]:
    """Build a local RAG index and retrieve testing context."""

    started = time.perf_counter()
    active_run_id = run_id or generate_run_id()
    prepared = _prepare_repository_metadata(
        repo_path=repo_path,
        repo_url=repo_url,
        project_info=project_info,
        indexed_documents=indexed_documents,
        run_id=active_run_id,
    )
    active_repo_path = prepared["repo_path"]
    active_project_info = prepared["project_info"]
    active_indexed_documents = prepared["indexed_documents"]
    if prepared["errors"]:
        rag_query = build_rag_agent_query(active_project_info, user_preferences, query)
        message = prepared["errors"][0]["message"]
        return _error_result(active_run_id, message, rag_query, active_repo_path)

    rag_query = build_rag_agent_query(active_project_info, user_preferences, query)
    source_paths = select_source_paths_for_rag(active_project_info, active_indexed_documents)
    index_result = index_project_documents(active_repo_path, source_paths, active_run_id)
    retrieval = retrieve_context_for_testing(
        index_path=index_result["index_path"],
        query=rag_query,
        top_k=top_k,
        project_info=active_project_info,
    )
    retrieved_context = [
        RetrievedContext(**item).model_dump(mode="json")
        for item in retrieval["retrieved_context"]
    ]
    missing_information = retrieval["missing_information"]
    if index_result["chunk_count"] == 0:
        missing_information = [
            *missing_information,
            "No readable source chunks were created for the selected RAG files.",
        ]

    status = "success" if retrieved_context and not missing_information else "partial"
    if not retrieved_context:
        status = "error"
    output = RAGAgentOutput(
        timestamp=current_timestamp(),
        status=status,
        duration_seconds=time.perf_counter() - started,
        query=rag_query,
        index_path=index_result["index_path"],
        chunk_count=index_result["chunk_count"],
        retrieved_context=retrieved_context,
        missing_information=missing_information,
        anomalies=[],
        metadata={
            "repo_url": repo_url,
            "repo_path": active_repo_path,
            "source_paths": source_paths,
            "source_count": index_result["source_count"],
            "manifest": index_result["manifest"],
        },
    )
    agent_output_path = _save_rag_output(output, active_run_id)
    retrieved_context_path = save_retrieved_context(active_run_id, retrieved_context)

    return {
        "run_id": active_run_id,
        "repo_path": active_repo_path,
        "rag_query": rag_query,
        "rag_index_path": index_result["index_path"],
        "chunk_count": index_result["chunk_count"],
        "retrieved_context": retrieved_context,
        "missing_information": missing_information,
        "agent_output_path": agent_output_path,
        "retrieved_context_path": retrieved_context_path,
        "errors": [],
        "agent_output": output.model_dump(mode="json"),
    }


def rag_node(state: TestAutomationState) -> dict[str, Any]:
    """LangGraph node for standalone RAG indexing and retrieval."""

    active_run_id = state.get("run_id") or generate_run_id()
    try:
        user_preferences = state.get("user_preferences") or {}
        result = run_rag_agent_alone(
            repo_path=state.get("repo_path"),
            repo_url=state.get("repo_url"),
            project_info=state.get("project_info"),
            indexed_documents=state.get("indexed_documents"),
            user_preferences=user_preferences,
            run_id=active_run_id,
            query=state.get("rag_query") or user_preferences.get("rag_query"),
            top_k=int(user_preferences.get("rag_top_k", 8) or 8),
        )
        return {
            "run_id": result["run_id"],
            "rag_index_path": result["rag_index_path"],
            "rag_query": result["rag_query"],
            "retrieved_context": result["retrieved_context"],
            "missing_information": result["missing_information"],
            "agent_logs": [*state.get("agent_logs", []), result["agent_output"]],
            "errors": [*state.get("errors", []), *result.get("errors", [])],
        }
    except Exception as error:
        output = create_error_output(
            "rag",
            error,
            metadata={"repo_path": state.get("repo_path"), "repo_url": state.get("repo_url")},
        )
        save_agent_output(output, active_run_id)
        return {
            "run_id": active_run_id,
            "rag_index_path": "",
            "rag_query": state.get("rag_query", ""),
            "retrieved_context": [],
            "missing_information": [str(error)],
            "agent_logs": [*state.get("agent_logs", []), output.model_dump(mode="json")],
            "errors": [
                *state.get("errors", []),
                {"agent": "rag", "field": "internal", "message": str(error)},
            ],
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the RAG Knowledge Agent alone.")
    parser.add_argument("--repo-url", default=None)
    parser.add_argument("--repo-path", default=None)
    parser.add_argument("--query", default=None)
    parser.add_argument("--top-k", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    """CLI entry point for the standalone RAG Knowledge Agent."""

    args = _parse_args()
    result = run_rag_agent_alone(
        repo_url=args.repo_url,
        repo_path=args.repo_path,
        query=args.query,
        top_k=args.top_k,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
