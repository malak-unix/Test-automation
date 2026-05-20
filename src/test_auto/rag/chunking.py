"""Chunk repository documents for the local deterministic RAG index."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from test_auto.shared.schemas import DocumentChunk
from test_auto.tools.repo_tools import read_text_file


def split_lines_with_numbers(text: str) -> list[tuple[int, str]]:
    """Return text lines numbered from 1."""

    return [(index, line) for index, line in enumerate(text.splitlines(), start=1)]


def detect_chunk_type(path: str) -> str:
    """Classify a repository path into a RAG chunk type."""

    lower = path.lower()
    name = Path(lower).name
    if name in {"readme.md", "readme.rst"} or lower.startswith("docs/") or lower.endswith((".md", ".rst")):
        return "doc"
    if name in {"urls.py", "views.py", "routers.py", "routes.py", "api.py", "serializers.py"}:
        return "api"
    if lower.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py"):
        return "test"
    if lower.startswith("templates/") or lower.endswith((".html", ".jsx", ".tsx")):
        return "ui"
    if name in {"requirements.txt", "pyproject.toml", "package.json", "docker-compose.yml"}:
        return "config"
    return "generic"


def _line_span(lines: list[tuple[int, str]]) -> tuple[int | None, int | None]:
    if not lines:
        return None, None
    return lines[0][0], lines[-1][0]


def _make_chunk(
    source_path: str,
    content: str,
    chunk_type: str,
    start_line: int | None,
    end_line: int | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    content = content.strip()
    if not content:
        return None
    return {
        "source_path": source_path,
        "chunk_type": chunk_type,
        "content": content,
        "start_line": start_line,
        "end_line": end_line,
        "metadata": metadata or {},
    }


def _split_numbered_lines(
    source_path: str,
    numbered_lines: list[tuple[int, str]],
    chunk_type: str,
    max_chars: int,
    overlap: int,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current: list[tuple[int, str]] = []

    for numbered_line in numbered_lines:
        if not current and len(numbered_line[1]) > max_chars:
            line_number, line = numbered_line
            step = max(1, max_chars - overlap)
            for start in range(0, len(line), step):
                segment = line[start : start + max_chars]
                chunk = _make_chunk(
                    source_path,
                    segment,
                    chunk_type,
                    line_number,
                    line_number,
                    metadata,
                )
                if chunk:
                    chunks.append(chunk)
            continue
        candidate = current + [numbered_line]
        candidate_text = "\n".join(line for _, line in candidate)
        if current and len(candidate_text) > max_chars:
            start_line, end_line = _line_span(current)
            chunk = _make_chunk(
                source_path,
                "\n".join(line for _, line in current),
                chunk_type,
                start_line,
                end_line,
                metadata,
            )
            if chunk:
                chunks.append(chunk)

            overlap_lines: list[tuple[int, str]] = []
            overlap_chars = 0
            for previous in reversed(current):
                overlap_lines.insert(0, previous)
                overlap_chars += len(previous[1]) + 1
                if overlap_chars >= overlap:
                    break
            current = overlap_lines + [numbered_line]
        else:
            current = candidate

    if current:
        start_line, end_line = _line_span(current)
        chunk = _make_chunk(
            source_path,
            "\n".join(line for _, line in current),
            chunk_type,
            start_line,
            end_line,
            metadata,
        )
        if chunk:
            chunks.append(chunk)

    return chunks


def chunk_generic(
    source_path: str,
    text: str,
    max_chars: int = 1200,
    overlap: int = 150,
) -> list[dict[str, Any]]:
    """Split any text into bounded chunks with line-aware overlap."""

    return _split_numbered_lines(
        source_path=source_path,
        numbered_lines=split_lines_with_numbers(text),
        chunk_type=detect_chunk_type(source_path),
        max_chars=max_chars,
        overlap=overlap,
    )


def chunk_markdown(
    source_path: str,
    text: str,
    max_chars: int = 1200,
    overlap: int = 150,
) -> list[dict[str, Any]]:
    """Split markdown by headings first, then by size if needed."""

    sections: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for line_number, line in split_lines_with_numbers(text):
        if line.lstrip().startswith("#") and current:
            sections.append(current)
            current = []
        current.append((line_number, line))
    if current:
        sections.append(current)

    chunks: list[dict[str, Any]] = []
    for section in sections:
        section_text = "\n".join(line for _, line in section)
        if len(section_text) <= max_chars:
            start_line, end_line = _line_span(section)
            chunk = _make_chunk(
                source_path,
                section_text,
                "doc",
                start_line,
                end_line,
                {"split_strategy": "markdown_heading"},
            )
            if chunk:
                chunks.append(chunk)
        else:
            chunks.extend(
                _split_numbered_lines(
                    source_path,
                    section,
                    "doc",
                    max_chars,
                    overlap,
                    {"split_strategy": "markdown_heading_overflow"},
                )
            )
    return chunks


def chunk_python(
    source_path: str,
    text: str,
    max_chars: int = 1600,
    overlap: int = 200,
) -> list[dict[str, Any]]:
    """Split Python around common route, class, and function boundaries."""

    boundary_pattern = re.compile(
        r"^\s*(def |class |urlpatterns\s*=|@\w+\.(?:get|post|put|delete|patch)|@router\.(?:get|post|put|delete|patch))",
        re.IGNORECASE,
    )
    blocks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for line_number, line in split_lines_with_numbers(text):
        if boundary_pattern.search(line) and current:
            blocks.append(current)
            current = []
        current.append((line_number, line))
    if current:
        blocks.append(current)

    if len(blocks) <= 1:
        return _split_numbered_lines(
            source_path,
            split_lines_with_numbers(text),
            detect_chunk_type(source_path),
            max_chars,
            overlap,
            {"split_strategy": "python_generic"},
        )

    chunks: list[dict[str, Any]] = []
    for block in blocks:
        block_text = "\n".join(line for _, line in block)
        if len(block_text) <= max_chars:
            start_line, end_line = _line_span(block)
            chunk = _make_chunk(
                source_path,
                block_text,
                detect_chunk_type(source_path),
                start_line,
                end_line,
                {"split_strategy": "python_boundary"},
            )
            if chunk:
                chunks.append(chunk)
        else:
            chunks.extend(
                _split_numbered_lines(
                    source_path,
                    block,
                    detect_chunk_type(source_path),
                    max_chars,
                    overlap,
                    {"split_strategy": "python_boundary_overflow"},
                )
            )
    return chunks


def chunk_document(source_path: str, text: str) -> list[dict[str, Any]]:
    """Chunk one repository document based on file type."""

    chunk_type = detect_chunk_type(source_path)
    if chunk_type == "doc":
        return chunk_markdown(source_path, text)
    if source_path.lower().endswith(".py"):
        return chunk_python(source_path, text)
    return chunk_generic(source_path, text)


def _stable_chunk_id(source_path: str, index: int, content: str) -> str:
    digest = hashlib.sha256(f"{source_path}:{index}:{content}".encode("utf-8")).hexdigest()[:12]
    safe_path = re.sub(r"[^a-zA-Z0-9]+", "_", source_path).strip("_").lower()
    return f"{safe_path}_{index}_{digest}"


def build_document_chunks(repo_path: str, source_paths: list[str]) -> list[dict[str, Any]]:
    """Read selected repository files safely and return validated chunk dicts."""

    chunks: list[dict[str, Any]] = []
    for source_path in source_paths:
        text = read_text_file(repo_path, source_path)
        if not text.strip():
            continue
        raw_chunks = chunk_document(source_path, text)
        for index, chunk in enumerate(raw_chunks):
            chunk["chunk_id"] = _stable_chunk_id(source_path, index, chunk["content"])
            chunk.setdefault("metadata", {})
            chunk["metadata"]["repo_path"] = str(Path(repo_path).resolve())
            chunks.append(DocumentChunk(**chunk).model_dump(mode="json"))
    return chunks
