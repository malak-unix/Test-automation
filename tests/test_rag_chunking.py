from __future__ import annotations

from pathlib import Path

from test_auto.rag.chunking import (
    build_document_chunks,
    chunk_generic,
    chunk_markdown,
    chunk_python,
    detect_chunk_type,
)


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_detect_chunk_type() -> None:
    assert detect_chunk_type("README.md") == "doc"
    assert detect_chunk_type("todo/views.py") == "api"
    assert detect_chunk_type("tests/test_api.py") == "test"
    assert detect_chunk_type("templates/login.html") == "ui"
    assert detect_chunk_type("requirements.txt") == "config"


def test_chunk_markdown_by_headings() -> None:
    text = "# Intro\nJWT auth\n\n## API\nTodo CRUD routes\n"

    chunks = chunk_markdown("README.md", text)

    assert len(chunks) >= 2
    assert all(chunk["source_path"] == "README.md" for chunk in chunks)


def test_chunk_python_detects_functions() -> None:
    text = "\n".join(
        [
            "def login(request):",
            "    pass",
            "",
            "class TodoViewSet:",
            "    def list(self):",
            "        pass",
        ]
    )

    chunks = chunk_python("todo/views.py", text)
    combined = "\n".join(chunk["content"] for chunk in chunks)

    assert "login" in combined
    assert "TodoViewSet" in combined


def test_chunk_generic_with_overlap() -> None:
    text = "a" * 5000

    chunks = chunk_generic("notes.txt", text, max_chars=1000, overlap=100)

    assert len(chunks) > 1


def test_build_document_chunks_reads_safe_files(tmp_path: Path) -> None:
    write_file(tmp_path, "README.md", "# API\nJWT todo CRUD\n")
    write_file(tmp_path, "todo/views.py", "def list_todos(request): pass\n")

    chunks = build_document_chunks(str(tmp_path), ["README.md", "todo/views.py"])

    assert chunks
    assert all(chunk["chunk_id"] for chunk in chunks)


def test_build_document_chunks_ignores_empty_files(tmp_path: Path) -> None:
    write_file(tmp_path, "empty.md", "")

    chunks = build_document_chunks(str(tmp_path), ["empty.md"])

    assert chunks == []
