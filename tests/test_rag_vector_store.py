from __future__ import annotations

from pathlib import Path

from test_auto.rag.embeddings import LocalHashEmbeddingModel, cosine_similarity
from test_auto.rag.vector_store import create_vector_store, load_vector_store, search_vector_store


def make_chunks() -> list[dict]:
    return [
        {
            "chunk_id": "auth_1",
            "source_path": "README.md",
            "chunk_type": "doc",
            "content": "JWT authentication login bearer token for todo API",
            "metadata": {},
        },
        {
            "chunk_id": "css_1",
            "source_path": "styles.css",
            "chunk_type": "ui",
            "content": "CSS styling colors layout buttons",
            "metadata": {},
        },
    ]


def test_local_hash_embedding_is_deterministic() -> None:
    model = LocalHashEmbeddingModel()

    assert model.embed_text("JWT login") == model.embed_text("JWT login")


def test_cosine_similarity_identical_vectors() -> None:
    model = LocalHashEmbeddingModel()
    vector = model.embed_text("JWT login authentication")

    assert cosine_similarity(vector, vector) > 0.99


def test_create_and_load_vector_store(tmp_path: Path) -> None:
    index_path = tmp_path / "rag_index"

    create_vector_store(make_chunks(), str(index_path))
    loaded = load_vector_store(str(index_path))

    assert (index_path / "chunks.json").exists()
    assert (index_path / "vectors.json").exists()
    assert (index_path / "manifest.json").exists()
    assert loaded["chunks"]
    assert loaded["vectors"]


def test_search_vector_store_returns_relevant_chunk(tmp_path: Path) -> None:
    index_path = tmp_path / "rag_index"
    create_vector_store(make_chunks(), str(index_path))

    results = search_vector_store(str(index_path), "JWT login authentication", top_k=1)

    assert results[0]["chunk_id"] == "auth_1"


def test_search_vector_store_handles_empty_query(tmp_path: Path) -> None:
    index_path = tmp_path / "rag_index"
    create_vector_store(make_chunks(), str(index_path))

    assert search_vector_store(str(index_path), "", top_k=2) == []
