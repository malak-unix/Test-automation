"""FastMCP testing tools server for milestone 15."""

from __future__ import annotations
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mcp.server.fastmcp import FastMCP

from test_auto.reporting.artifact_loader import safe_load_json
from test_auto.reporting.html_renderer import render_report_html
from test_auto.shared.utils import ensure_directory, validate_url, write_json_file
from test_auto.tools.api_tools import (
    mask_sensitive_headers,
    send_http_request,
)
from test_auto.tools.bug_tools import mask_sensitive_values
from test_auto.tools.repo_tools import (
    clone_repository,
    is_probably_git_url,
    list_project_files,
    read_text_file,
)


SERVER_NAME = "testing-tools-server"
TOOLS_VERSION = "0.1.0"
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
mcp = FastMCP(SERVER_NAME)


def _success(payload: dict[str, Any]) -> dict[str, Any]:
    return mask_sensitive_values(payload)


def _is_safe_relative_path(relative_path: str) -> bool:
    path = Path(relative_path)
    return bool(relative_path) and not path.is_absolute() and ".." not in path.parts


def _safe_repo_file(repo_path: str, relative_path: str) -> bool:
    if not _is_safe_relative_path(relative_path):
        return False
    try:
        root = Path(repo_path).expanduser().resolve()
        target = (root / relative_path).resolve()
        target.relative_to(root)
        return target.is_file()
    except (OSError, ValueError):
        return False


def _sanitize_artifact_name(name: str) -> str | None:
    if not name or any(part in name for part in ("/", "\\", "..")):
        return None
    stem = name[:-5] if name.endswith(".json") else name
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", stem):
        return None
    return stem


def _safe_output_html_path(output_path: str | None, run_id: str) -> Path:
    if output_path:
        candidate = Path(output_path)
    else:
        candidate = Path("reports") / "generated" / f"report_{run_id}_mcp.html"
    reports_dir = (Path.cwd() / "reports" / "generated").resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(reports_dir)
    except ValueError:
        return reports_dir / f"report_{run_id}_mcp.html"
    return resolved


@mcp.tool()
def health_check() -> dict[str, Any]:
    """Return server health information. Use this to verify that the testing tools MCP server is running."""

    return {
        "status": "ok",
        "server": SERVER_NAME,
        "tools_version": TOOLS_VERSION,
    }


@mcp.tool()
def validate_url_tool(url: str) -> dict[str, Any]:
    """Validate whether a string looks like an HTTP, HTTPS, or GitHub/Git URL. Use this before repository or HTTP testing actions."""

    if is_probably_git_url(url):
        url_type = "git"
        is_valid = True
    elif validate_url(url):
        url_type = "http"
        is_valid = True
    else:
        url_type = "unknown"
        is_valid = False
    return {"url": url, "is_valid": is_valid, "type": url_type}


@mcp.tool()
def list_project_files_tool(repo_path: str, max_files: int = 200) -> dict[str, Any]:
    """List safe project files from a local repository path. Use this to inspect repository structure without executing code."""

    try:
        root = Path(repo_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return {
                "status": "error",
                "repo_path": str(root),
                "files": [],
                "count": 0,
                "error": "repo_path does not exist or is not a directory.",
            }
        files = list_project_files(str(root), max_files=max(1, min(int(max_files), 1000)))
        return {
            "status": "success",
            "repo_path": str(root),
            "files": files,
            "count": len(files),
            "error": None,
        }
    except Exception as error:
        return {
            "status": "error",
            "repo_path": repo_path,
            "files": [],
            "count": 0,
            "error": str(error),
        }


@mcp.tool()
def read_text_file_tool(
    repo_path: str,
    relative_path: str,
    max_chars: int = 10000,
) -> dict[str, Any]:
    """Read one safe text file from a repository. Use this to inspect README, route files, templates, and tests. Path traversal is not allowed."""

    try:
        root = Path(repo_path).expanduser().resolve()
        if not _safe_repo_file(str(root), relative_path):
            return {
                "status": "error",
                "repo_path": str(root),
                "relative_path": relative_path,
                "content": "",
                "chars": 0,
                "error": "File is missing or relative_path is unsafe.",
            }
        content = read_text_file(
            str(root),
            relative_path,
            max_chars=max(1, min(int(max_chars), 100000)),
        )
        return {
            "status": "success",
            "repo_path": str(root),
            "relative_path": relative_path,
            "content": content,
            "chars": len(content),
            "error": None,
        }
    except Exception as error:
        return {
            "status": "error",
            "repo_path": repo_path,
            "relative_path": relative_path,
            "content": "",
            "chars": 0,
            "error": str(error),
        }


@mcp.tool()
def clone_repository_tool(
    repo_url: str,
    run_id: str,
    results_dir: str = "results",
) -> dict[str, Any]:
    """Clone a GitHub repository into results/runs/<run_id>/repo for read-only analysis. Use this only for trusted public repositories."""

    try:
        result = clone_repository(repo_url, run_id, results_dir=results_dir)
        return _success(result)
    except Exception as error:
        return {
            "status": "error",
            "repo_path": "",
            "details": "Repository clone failed.",
            "error": str(error),
        }


@mcp.tool()
def send_http_request_tool(
    method: str,
    url: str,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    timeout_seconds: int = 5,
    allow_mutating: bool = False,
) -> dict[str, Any]:
    """Send one safe HTTP request to a target application and return status, duration, and short response preview. Mutating methods are disabled unless allow_mutating is true."""

    method_upper = str(method or "").upper()
    if method_upper in MUTATING_METHODS and not allow_mutating:
        return {
            "status": "skipped",
            "method": method_upper,
            "url": url,
            "status_code": None,
            "duration_ms": None,
            "text_preview": "",
            "json_preview": None,
            "request_headers": mask_sensitive_headers(headers),
            "error": None,
            "error_type": "safety",
            "details": "Mutating HTTP methods are disabled by default.",
        }
    response = send_http_request(
        method=method_upper,
        url=url,
        headers=headers,
        json_body=json_body,
        timeout_seconds=max(1, min(int(timeout_seconds), 30)),
    )
    status = "success" if response.get("ok") else (response.get("error_type") or "error")
    return _success(
        {
            "status": status,
            "method": method_upper,
            "url": url,
            "status_code": response.get("status_code"),
            "duration_ms": response.get("duration_ms"),
            "text_preview": str(response.get("text_preview") or "")[:500],
            "json_preview": response.get("json_preview"),
            "request_headers": mask_sensitive_headers(headers),
            "error": response.get("error"),
            "error_type": response.get("error_type"),
            "details": response.get("error") or "HTTP request completed.",
        }
    )


@mcp.tool()
def generate_html_report_tool(
    final_results_path: str,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Generate or copy an HTML report from an existing final_results.json artifact. Use this after test results have been aggregated."""

    try:
        final_results = safe_load_json(final_results_path)
        if not final_results:
            return {
                "status": "error",
                "report_html_path": "",
                "error": "final_results_path is missing or unreadable.",
            }
        run_id = str(final_results.get("run_id") or "mcp_report")
        html = render_report_html(mask_sensitive_values(final_results))
        path = _safe_output_html_path(output_path, run_id)
        ensure_directory(path.parent)
        path.write_text(html, encoding="utf-8")
        return {
            "status": "success",
            "report_html_path": str(path),
            "error": None,
        }
    except Exception as error:
        return {
            "status": "error",
            "report_html_path": "",
            "error": str(error),
        }


@mcp.tool()
def save_json_artifact_tool(
    run_id: str,
    name: str,
    payload: dict[str, Any],
    results_dir: str = "results",
) -> dict[str, Any]:
    """Save a JSON artifact under results/runs/<run_id>/<name>.json. Use this for MCP tool demonstrations and structured outputs."""

    safe_name = _sanitize_artifact_name(name)
    if not safe_name:
        return {
            "status": "error",
            "path": "",
            "error": "Artifact name is unsafe.",
        }
    run_dir = ensure_directory(Path(results_dir) / "runs" / run_id)
    path = run_dir / f"{safe_name}.json"
    write_json_file(path, mask_sensitive_values(payload or {}))
    return {
        "status": "success",
        "path": str(path),
        "error": None,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the testing tools MCP server.")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> None:
    """CLI entry point for stdio MCP server or self-test mode."""

    args = _parse_args()
    if args.self_test:
        print(json.dumps(health_check(), indent=2))
        return
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
