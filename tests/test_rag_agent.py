from __future__ import annotations

from pathlib import Path

from test_auto.agents.rag_agent import rag_node, run_rag_agent_alone
from test_auto.graph.rag_workflow import run_rag_workflow


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_fake_django_rest_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_rag_repo"
    write_file(
        repo,
        "README.md",
        "# Todo API\nJWT authentication protects Todo CRUD API routes.\n",
    )
    write_file(
        repo,
        "requirements.txt",
        "django\ndjangorestframework\ndjangorestframework-simplejwt\npytest\n",
    )
    write_file(repo, "todo/urls.py", 'path("api/todos/", views.todo_list)\n')
    write_file(
        repo,
        "todo/views.py",
        "def list_todos(request): pass\n"
        "def create_todo(request): pass\n"
        "def update_todo(request): pass\n"
        "def delete_todo(request): pass\n",
    )
    write_file(repo, "templates/login.html", "<form>JWT login</form>\n")
    write_file(repo, "tests/test_todo_api.py", "def test_todo_list(): assert True\n")
    return repo


def project_info() -> dict:
    return {
        "language": "Python",
        "framework": "Django REST Framework",
        "has_api": True,
        "has_ui": True,
        "auth_type": "JWT",
        "candidate_docs": ["README.md"],
        "candidate_api_files": ["todo/urls.py", "todo/views.py"],
        "candidate_ui_files": ["templates/login.html"],
        "test_dirs": ["tests/test_todo_api.py"],
    }


def indexed_documents() -> list[dict]:
    return [
        {"path": "README.md", "type": "doc", "reason": "docs"},
        {"path": "todo/urls.py", "type": "api", "reason": "routes"},
        {"path": "todo/views.py", "type": "api", "reason": "views"},
        {"path": "templates/login.html", "type": "ui", "reason": "ui"},
        {"path": "tests/test_todo_api.py", "type": "test", "reason": "tests"},
    ]


def test_run_rag_agent_alone_fake_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    repo = make_fake_django_rest_repo(tmp_path)

    result = run_rag_agent_alone(
        repo_path=str(repo),
        project_info=project_info(),
        indexed_documents=indexed_documents(),
        query="JWT authentication todo CRUD API tests",
    )

    assert result["run_id"]
    assert Path(result["rag_index_path"]).exists()
    assert result["chunk_count"] > 0
    assert isinstance(result["retrieved_context"], list)
    assert Path(result["agent_output_path"]).exists()
    assert Path(result["retrieved_context_path"]).exists()
    assert (Path(result["rag_index_path"]) / "manifest.json").exists()


def test_rag_node_returns_state_patch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    repo = make_fake_django_rest_repo(tmp_path)

    update = rag_node(
        {
            "run_id": "test_run",
            "repo_path": str(repo),
            "project_info": project_info(),
            "indexed_documents": indexed_documents(),
            "user_preferences": {
                "focus": "JWT authentication todo CRUD",
                "test_types": ["api"],
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    assert update["rag_index_path"]
    assert update["rag_query"]
    assert "retrieved_context" in update
    assert "missing_information" in update
    assert update["agent_logs"]


def test_rag_workflow_fake_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    repo = make_fake_django_rest_repo(tmp_path)

    final_state = run_rag_workflow(
        {
            "run_id": "rag_workflow_test",
            "repo_path": str(repo),
            "project_info": project_info(),
            "indexed_documents": indexed_documents(),
            "rag_query": "JWT authentication todo CRUD API tests",
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state["retrieved_context"]


def test_rag_agent_handles_missing_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_rag_agent_alone(repo_path=str(tmp_path / "missing"))

    assert result["errors"]
    assert result["agent_output"]["status"] == "error"
