"""Repository Analyzer Agent.

Role in the architecture: safely inspect a local or cloned repository and return
compact project metadata, endpoints, UI flow hints, and files useful for RAG.
It reads files only; it never starts the target app or runs repository code.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from test_auto.agents.base import create_error_output, save_agent_output
from test_auto.graph.state import TestAutomationState
from test_auto.mcp.tool_router import build_mcp_agent_log, call_mcp_or_local, should_use_mcp
from test_auto.shared.schemas import ProjectInfo, RepositoryAnalyzerOutput
from test_auto.shared.utils import current_timestamp, ensure_directory, generate_run_id, write_json_file
from test_auto.tools.repo_tools import (
    build_project_info,
    clone_repository,
    discover_python_endpoints,
    discover_ui_flows,
    list_project_files,
    resolve_repo_path,
    select_indexed_documents,
)


REPO_ANALYZER_SYSTEM_PROMPT = """
You are the Repository Analyzer Agent.
Inspect the repository using tools and return structured project metadata.
Do not generate tests.
Do not modify source code.
Only report evidence you can support from files.
Return strict JSON: language, framework, has_api, has_ui, docs, routes, tests, risks.
"""


def _unknown_project_info(risks: list[str] | None = None) -> dict[str, Any]:
    return ProjectInfo(
        language="Unknown",
        framework="Unknown",
        test_framework=None,
        has_api=False,
        has_ui=False,
        auth_type=None,
        package_manager=None,
        source_dirs=[],
        test_dirs=[],
        candidate_docs=[],
        candidate_api_files=[],
        candidate_ui_files=[],
        risks=risks or [],
    ).model_dump(mode="json")


def _save_repository_outputs(
    output: RepositoryAnalyzerOutput,
    run_id: str,
    project_info: dict[str, Any],
) -> tuple[str, str]:
    run_dir = ensure_directory(Path("results") / "runs" / run_id)
    agent_output_path = write_json_file(
        run_dir / "repo_analyzer_result.json",
        output.model_dump(mode="json"),
    )
    project_info_path = write_json_file(run_dir / "project_info.json", project_info)
    return str(agent_output_path), str(project_info_path)


def _local_list_project_files(repo_path: str, max_files: int = 500) -> dict[str, Any]:
    return {
        "status": "success",
        "repo_path": repo_path,
        "files": list_project_files(repo_path, max_files=max_files),
        "error": None,
    }


def _tool_backend(events: list[dict[str, Any]]) -> str:
    if any(event.get("fallback_used") for event in events):
        return "mixed"
    if not events or not any(event.get("used_mcp") for event in events):
        return "local"
    return "mcp"


def _resolve_repository_with_optional_mcp(
    repo_url: str | None,
    repo_path: str | None,
    run_id: str,
    user_preferences: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if should_use_mcp(user_preferences) and repo_url and not repo_path:
        routed = call_mcp_or_local(
            tool_name="clone_repository_tool",
            mcp_args={"repo_url": repo_url, "run_id": run_id, "results_dir": "results"},
            local_callable=clone_repository,
            local_args={"repo_url": repo_url, "run_id": run_id, "results_dir": "results"},
            user_preferences=user_preferences,
        )
        event = build_mcp_agent_log(
            "clone_repository_tool",
            used_mcp=routed.get("used_mcp", False),
            fallback_used=routed.get("fallback_used", False),
            error=routed.get("mcp_error") or routed.get("error"),
        )
        return routed.get("result") or {}, [event]
    return resolve_repo_path(repo_url, repo_path, run_id), []


def _list_files_with_optional_mcp(
    repo_path: str,
    user_preferences: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    if not should_use_mcp(user_preferences):
        return list_project_files(repo_path), []

    routed = call_mcp_or_local(
        tool_name="list_project_files_tool",
        mcp_args={"repo_path": repo_path, "max_files": 500},
        local_callable=_local_list_project_files,
        local_args={"repo_path": repo_path, "max_files": 500},
        user_preferences=user_preferences,
    )
    result = routed.get("result") or {}
    files = result.get("files", []) if isinstance(result, dict) else result
    event = build_mcp_agent_log(
        "list_project_files_tool",
        used_mcp=routed.get("used_mcp", False),
        fallback_used=routed.get("fallback_used", False),
        error=routed.get("mcp_error") or routed.get("error"),
    )
    return list(files or []), [event]


def analyze_repository(
    repo_url: str | None = None,
    repo_path: str | None = None,
    run_id: str | None = None,
    user_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze a local or cloned repository and save structured JSON evidence."""

    started = time.perf_counter()
    active_run_id = run_id or generate_run_id()
    preferences = user_preferences or {}
    resolved, mcp_events = _resolve_repository_with_optional_mcp(
        repo_url,
        repo_path,
        active_run_id,
        preferences,
    )
    tool_backend = _tool_backend(mcp_events)
    mcp_fallback_used = any(event.get("fallback_used") for event in mcp_events)

    if resolved["status"] != "success":
        error = {
            "agent": "repo_analyzer",
            "field": "repo_path",
            "message": resolved.get("error") or resolved["details"],
        }
        project_info = _unknown_project_info([error["message"]])
        output = RepositoryAnalyzerOutput(
            timestamp=current_timestamp(),
            status="error",
            duration_seconds=time.perf_counter() - started,
            project_info=ProjectInfo(**project_info),
            discovered_endpoints=[],
            discovered_ui_flows=[],
            indexed_documents=[],
            anomalies=[error],
            metadata={
                "repo_url": repo_url,
                "repo_path": repo_path,
                "resolve_details": resolved,
                "tool_backend": tool_backend,
                "mcp_fallback_used": mcp_fallback_used,
                "mcp_events": mcp_events,
            },
        )
        agent_output_path, project_info_path = _save_repository_outputs(
            output,
            active_run_id,
            project_info,
        )
        return {
            "run_id": active_run_id,
            "repo_path": resolved.get("repo_path", ""),
            "project_info": project_info,
            "discovered_endpoints": [],
            "discovered_ui_flows": [],
            "indexed_documents": [],
            "agent_output_path": agent_output_path,
            "project_info_path": project_info_path,
            "errors": [error],
            "agent_output": output.model_dump(mode="json"),
            "tool_backend": tool_backend,
            "mcp_fallback_used": mcp_fallback_used,
        }

    active_repo_path = resolved["repo_path"]
    files, list_events = _list_files_with_optional_mcp(active_repo_path, preferences)
    mcp_events.extend(list_events)
    tool_backend = _tool_backend(mcp_events)
    mcp_fallback_used = any(event.get("fallback_used") for event in mcp_events)
    project_info = build_project_info(active_repo_path, files)
    endpoints = discover_python_endpoints(
        active_repo_path,
        project_info["candidate_api_files"],
    )
    ui_flows = discover_ui_flows(project_info["candidate_ui_files"])
    indexed_documents = select_indexed_documents(project_info)

    output = RepositoryAnalyzerOutput(
        timestamp=current_timestamp(),
        status="success",
        duration_seconds=time.perf_counter() - started,
        project_info=ProjectInfo(**project_info),
        discovered_endpoints=endpoints,
        discovered_ui_flows=ui_flows,
        indexed_documents=indexed_documents,
        anomalies=[],
        metadata={
            "repo_url": repo_url,
            "repo_path": active_repo_path,
            "file_count": len(files),
            "resolve_details": resolved,
            "tool_backend": tool_backend,
            "mcp_fallback_used": mcp_fallback_used,
            "mcp_events": mcp_events,
        },
    )
    agent_output_path, project_info_path = _save_repository_outputs(
        output,
        active_run_id,
        project_info,
    )

    return {
        "run_id": active_run_id,
        "repo_path": active_repo_path,
        "project_info": project_info,
        "discovered_endpoints": endpoints,
        "discovered_ui_flows": ui_flows,
        "indexed_documents": indexed_documents,
        "agent_output_path": agent_output_path,
        "project_info_path": project_info_path,
        "errors": [],
        "agent_output": output.model_dump(mode="json"),
        "tool_backend": tool_backend,
        "mcp_fallback_used": mcp_fallback_used,
    }


def repo_analyzer_node(state: TestAutomationState) -> dict[str, Any]:
    """LangGraph node that returns a partial State update for repo analysis."""

    active_run_id = state.get("run_id") or generate_run_id()
    try:
        result = analyze_repository(
            repo_url=state.get("repo_url"),
            repo_path=state.get("repo_path"),
            run_id=active_run_id,
            user_preferences=state.get("user_preferences") or {},
        )
        return {
            "run_id": result["run_id"],
            "repo_path": result["repo_path"],
            "project_info": result["project_info"],
            "discovered_endpoints": result["discovered_endpoints"],
            "discovered_ui_flows": result["discovered_ui_flows"],
            "indexed_documents": result["indexed_documents"],
            "agent_logs": [
                *state.get("agent_logs", []),
                result["agent_output"],
            ],
            "errors": [
                *state.get("errors", []),
                *result.get("errors", []),
            ],
        }
    except Exception as error:
        output = create_error_output(
            "repo_analyzer",
            error,
            metadata={
                "repo_url": state.get("repo_url"),
                "repo_path": state.get("repo_path"),
            },
        )
        save_agent_output(output, active_run_id)
        return {
            "run_id": active_run_id,
            "repo_path": state.get("repo_path", ""),
            "project_info": _unknown_project_info([str(error)]),
            "discovered_endpoints": [],
            "discovered_ui_flows": [],
            "indexed_documents": [],
            "agent_logs": [*state.get("agent_logs", []), output.model_dump(mode="json")],
            "errors": [
                *state.get("errors", []),
                {
                    "agent": "repo_analyzer",
                    "field": "internal",
                    "message": str(error),
                },
            ],
        }


def run_repo_analyzer_alone(
    repo_url: str | None = None,
    repo_path: str | None = None,
) -> dict[str, Any]:
    """Convenience wrapper for the standalone Repository Analyzer."""

    return analyze_repository(repo_url=repo_url, repo_path=repo_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Repository Analyzer Agent alone.")
    parser.add_argument("--repo-url", default=None)
    parser.add_argument("--repo-path", default=None)
    return parser.parse_args()


def main() -> None:
    """CLI entry point for standalone repository analysis."""

    args = _parse_args()
    result = run_repo_analyzer_alone(repo_url=args.repo_url, repo_path=args.repo_path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
