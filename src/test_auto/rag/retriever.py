"""Higher-level local RAG retrieval helpers."""

from __future__ import annotations

from typing import Any

from test_auto.rag.vector_store import search_vector_store


def build_default_rag_query(
    project_info: dict[str, Any],
    user_preferences: dict[str, Any] | None = None,
) -> str:
    """Build a testing-oriented retrieval query from project metadata."""

    preferences = user_preferences or {}
    parts: list[str] = []
    focus = preferences.get("focus")
    if focus:
        parts.append(str(focus))
    test_types = preferences.get("test_types") or []
    if isinstance(test_types, str):
        test_types = [test_types]
    parts.extend(str(item) for item in test_types)
    parts.append(str(project_info.get("framework", "")))
    parts.append(str(project_info.get("auth_type", "")))
    if project_info.get("has_api"):
        parts.append("API routes CRUD endpoints")
    if project_info.get("has_ui"):
        parts.append("UI templates login navigation")
    query = " ".join(part for part in parts if part and part != "None").strip()
    return query or "JWT authentication todo CRUD API UI routes tests"


def assess_context_strength(
    retrieved_context: list[dict[str, Any]],
    query: str,
    project_info: dict[str, Any] | None = None,
) -> list[str]:
    """Return warnings when retrieved context appears weak or incomplete."""

    missing: list[str] = []
    info = project_info or {}
    if not retrieved_context:
        return ["No chunks were retrieved for the RAG query."]
    if all(item.get("score", 0.0) < 0.08 for item in retrieved_context):
        missing.append("Retrieved chunks have low similarity scores.")

    chunk_types = {item.get("chunk_type") for item in retrieved_context}
    combined = "\n".join(item.get("content", "") for item in retrieved_context).lower()
    if info.get("has_api") and "api" not in chunk_types:
        missing.append("No API evidence was retrieved even though the project has API files.")
    if info.get("auth_type") == "JWT" and "jwt" not in combined:
        missing.append("No JWT evidence was retrieved even though auth_type is JWT.")
    if info.get("has_ui") and "ui" not in chunk_types:
        missing.append("No UI evidence was retrieved even though the project has UI files.")
    if query and not any(term in combined for term in query.lower().split()[:6]):
        missing.append("Retrieved context weakly overlaps with the query terms.")
    return missing


def retrieve_context_for_testing(
    index_path: str,
    query: str,
    top_k: int = 8,
    project_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Retrieve context for downstream test planning without generating tests."""

    retrieved_context = search_vector_store(index_path, query, top_k=top_k)
    missing_information = assess_context_strength(retrieved_context, query, project_info)
    return {
        "query": query,
        "retrieved_context": retrieved_context,
        "missing_information": missing_information,
    }
