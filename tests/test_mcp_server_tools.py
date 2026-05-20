from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcp_servers.testing_tools_server import (
    health_check,
    list_project_files_tool,
    read_text_file_tool,
    save_json_artifact_tool,
    send_http_request_tool,
    validate_url_tool,
)


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_health_check_direct() -> None:
    assert health_check()["status"] == "ok"


def test_validate_url_tool() -> None:
    assert validate_url_tool("https://github.com/Vitaee/DjangoRestAPI")["is_valid"] is True
    assert validate_url_tool("https://github.com/Vitaee/DjangoRestAPI")["type"] == "git"
    assert validate_url_tool("http://localhost:8000")["type"] == "http"
    assert validate_url_tool("not-a-url")["is_valid"] is False


def test_list_project_files_tool_fake_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_file(repo, "README.md", "# Demo")
    write_file(repo, "todo/urls.py", "urlpatterns = []")
    write_file(repo, ".git/config", "ignored")
    write_file(repo, "node_modules/a.js", "ignored")

    result = list_project_files_tool(str(repo))

    assert result["status"] == "success"
    assert "README.md" in result["files"]
    assert "todo/urls.py" in result["files"]
    assert ".git/config" not in result["files"]
    assert "node_modules/a.js" not in result["files"]


def test_read_text_file_tool_fake_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_file(repo, "README.md", "# Demo")

    result = read_text_file_tool(str(repo), "README.md")

    assert result["status"] == "success"
    assert "Demo" in result["content"]


def test_read_text_file_tool_blocks_path_traversal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(tmp_path, "secret.txt", "secret")

    result = read_text_file_tool(str(repo), "../secret.txt")

    assert result["status"] == "error"
    assert result["content"] == ""


def test_send_http_request_tool_skips_mutating_by_default() -> None:
    result = send_http_request_tool("POST", "http://localhost:8000/api/todos/")

    assert result["status"] == "skipped"
    assert "Mutating HTTP methods are disabled" in result["details"]


def test_send_http_request_tool_environment_error() -> None:
    result = send_http_request_tool("GET", "http://127.0.0.1:9", timeout_seconds=1)

    assert result["status"] in {"environment_error", "error"}


def test_save_json_artifact_tool(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = save_json_artifact_tool("mcp_test_run", "demo", {"ok": True})

    assert result["status"] == "success"
    assert Path(result["path"]).exists()
    assert "demo.json" in result["path"]


def test_save_json_artifact_tool_rejects_bad_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = save_json_artifact_tool("mcp_test_run", "../bad", {"ok": True})

    assert result["status"] == "error"


def test_server_self_test_subprocess() -> None:
    result = subprocess.run(
        [sys.executable, "mcp_servers/testing_tools_server.py", "--self-test"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
