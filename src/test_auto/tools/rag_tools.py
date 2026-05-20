"""Local RAG tools for indexing and retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from test_auto.rag.chunking import build_document_chunks
from test_auto.rag.retriever import retrieve_context_for_testing
from test_auto.rag.vector_store import create_vector_store


def select_source_paths_for_rag(
    project_info: dict[str, Any],
    indexed_documents: list[dict[str, Any]] | None = None,
    max_files: int = 40,
) -> list[str]:
    """Select repository-relative files to chunk for the local RAG index."""

    selected: list[str] = []

    def add(path: str | None) -> None:
        if path and path not in selected:
            selected.append(path)

    for item in indexed_documents or []:
        add(item.get("path"))

    for key in (
        "candidate_docs",
        "candidate_api_files",
        "candidate_ui_files",
        "test_dirs",
    ):
        for path in project_info.get(key, []) or []:
            add(path)

    return selected[:max_files]


def index_project_documents(
    repo_path: str,
    source_paths: list[str],
    run_id: str,
    results_dir: str = "results",
) -> dict[str, Any]:
    """Chunk selected repository files and build a local JSON vector index."""

    index_path = Path(results_dir) / "runs" / run_id / "rag_index"
    chunks = build_document_chunks(repo_path, source_paths)
    manifest = create_vector_store(chunks, str(index_path))
    return {
        "index_path": str(index_path),
        "chunk_count": len(chunks),
        "source_count": len({chunk["source_path"] for chunk in chunks}),
        "manifest": manifest,
    }


def retrieve_project_context(
    index_path: str,
    query: str,
    top_k: int = 8,
) -> dict[str, Any]:
    """Retrieve testing context from the local vector index."""

    return retrieve_context_for_testing(index_path=index_path, query=query, top_k=top_k)
