"""Pure-Python deterministic embeddings for the local MVP RAG baseline."""

from __future__ import annotations

import hashlib
import math
import re


def tokenize_for_embedding(text: str) -> list[str]:
    """Lowercase text and extract stable word/number tokens."""

    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    keep_short = {"api", "ui", "db", "id"}
    return [token for token in tokens if len(token) > 2 or token in keep_short]


class LocalHashEmbeddingModel:
    """Deterministic local embedding model replaceable by stronger embeddings later."""

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        """Embed text with SHA-256 token hashing and unit normalization."""

        vector = [0.0 for _ in range(self.dimensions)]
        for token in tokenize_for_embedding(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple documents."""

        return [self.embed_text(text) for text in texts]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Return cosine similarity normalized to the 0..1 range."""

    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    norm_a = math.sqrt(sum(value * value for value in vec_a))
    norm_b = math.sqrt(sum(value * value for value in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    score = sum(a * b for a, b in zip(vec_a, vec_b)) / (norm_a * norm_b)
    return max(0.0, min(1.0, score))
