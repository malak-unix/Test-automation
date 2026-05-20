"""Small JSON vector store for local deterministic RAG."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from test_auto.rag.embeddings import (
    LocalHashEmbeddingModel,
    cosine_similarity,
    tokenize_for_embedding,
)
from test_auto.shared.schemas import RAGIndexManifest
from test_auto.shared.utils import current_timestamp, ensure_directory, write_json_file


def create_vector_store(
    chunks: list[dict[str, Any]],
    index_path: str,
    embedding_model: LocalHashEmbeddingModel | None = None,
) -> dict[str, Any]:
    """Embed chunks and save chunks, vectors, and manifest as JSON files."""

    model = embedding_model or LocalHashEmbeddingModel()
    index_dir = ensure_directory(index_path)
    vectors = model.embed_documents([chunk["content"] for chunk in chunks])
    indexed_sources = sorted({chunk["source_path"] for chunk in chunks})
    repo_path = ""
    if chunks:
        repo_path = chunks[0].get("metadata", {}).get("repo_path", "")
    manifest = RAGIndexManifest(
        run_id=Path(index_dir).parent.name,
        repo_path=repo_path,
        index_path=str(index_dir),
        total_files=len(indexed_sources),
        total_chunks=len(chunks),
        embedding_backend=f"local_hash:{model.dimensions}",
        created_at=current_timestamp(),
        indexed_sources=indexed_sources,
    ).model_dump(mode="json")

    write_json_file(index_dir / "chunks.json", {"chunks": chunks})
    write_json_file(index_dir / "vectors.json", {"vectors": vectors})
    write_json_file(index_dir / "manifest.json", manifest)
    return manifest


def load_vector_store(index_path: str) -> dict[str, Any]:
    """Load chunks, vectors, and manifest from a local JSON vector store."""

    index_dir = Path(index_path)
    chunks = _read_json(index_dir / "chunks.json").get("chunks", [])
    vectors = _read_json(index_dir / "vectors.json").get("vectors", [])
    manifest = _read_json(index_dir / "manifest.json")
    return {"chunks": chunks, "vectors": vectors, "manifest": manifest}


def _read_json(path: Path) -> dict[str, Any]:
    import json

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _build_reason(query: str, content: str) -> str:
    query_terms = set(tokenize_for_embedding(query))
    content_terms = set(tokenize_for_embedding(content))
    matched = sorted(query_terms & content_terms)[:5]
    if matched:
        return "Matched query terms related to " + ", ".join(matched) + "."
    return "Retrieved by local hash-vector similarity."


def search_vector_store(
    index_path: str,
    query: str,
    top_k: int = 5,
    embedding_model: LocalHashEmbeddingModel | None = None,
) -> list[dict[str, Any]]:
    """Search the local vector store for the chunks most relevant to a query."""

    if not query.strip():
        return []
    model = embedding_model or LocalHashEmbeddingModel()
    store = load_vector_store(index_path)
    chunks = store.get("chunks", [])
    vectors = store.get("vectors", [])
    query_vector = model.embed_text(query)

    scored: list[dict[str, Any]] = []
    for chunk, vector in zip(chunks, vectors):
        score = cosine_similarity(query_vector, vector)
        scored.append(
            {
                "chunk_id": chunk["chunk_id"],
                "source_path": chunk["source_path"],
                "content": chunk["content"],
                "score": score,
                "reason": _build_reason(query, chunk["content"]),
                "chunk_type": chunk.get("chunk_type"),
                "metadata": chunk.get("metadata", {}),
            }
        )

    return sorted(scored, key=lambda item: item["score"], reverse=True)[:top_k]


def save_retrieved_context(
    run_id: str,
    retrieved_context: list[dict[str, Any]],
    results_dir: str = "results",
) -> str:
    """Save retrieved context under results/runs/<run_id>/retrieved_context.json."""

    path = Path(results_dir) / "runs" / run_id / "retrieved_context.json"
    write_json_file(path, {"retrieved_context": retrieved_context})
    return str(path)
