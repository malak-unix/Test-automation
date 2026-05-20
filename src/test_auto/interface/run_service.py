"""Service layer that connects Flask forms to the LangGraph workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from test_auto.graph.workflow import run_workflow
from test_auto.interface.dashboard_helpers import (
    mask_sensitive_for_display,
    safe_artifact_path,
)
from test_auto.shared.utils import json_safe


DEFAULT_REPO_URL = "https://github.com/Vitaee/DjangoRestAPI"
DEFAULT_TARGET_URL = "http://localhost:8000"
DEFAULT_FOCUS = "JWT authentication todo CRUD API tests"


def _get_value(form_data: Any, key: str, default: Any = "") -> Any:
    if hasattr(form_data, "get"):
        return form_data.get(key, default)
    return default


def _get_list(form_data: Any, key: str) -> list[str]:
    if hasattr(form_data, "getlist"):
        values = form_data.getlist(key)
    else:
        raw = (form_data or {}).get(key, [])
        values = raw if isinstance(raw, list) else [raw] if raw else []
    return [str(value) for value in values if str(value).strip()]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "llm"}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _compact_agent_logs(agent_logs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return small dashboard-safe log entries."""

    compact: list[dict[str, Any]] = []
    for index, log in enumerate(agent_logs or [], start=1):
        if not isinstance(log, dict):
            continue
        metadata = log.get("metadata") or {}
        summary = log.get("summary") or {}
        resolve_details = metadata.get("resolve_details")
        message = log.get("message") or log.get("reasoning_summary")
        if not message and isinstance(resolve_details, dict):
            message = resolve_details.get("details")
        if not message:
            message = f"{log.get('agent', 'agent')} completed with status {log.get('status', 'unknown')}."
        compact.append(
            {
                "index": index,
                "agent": log.get("agent", "unknown"),
                "status": log.get("status", "unknown"),
                "timestamp": log.get("timestamp", ""),
                "duration_seconds": log.get("duration_seconds"),
                "message": str(message)[:240],
                "total_tests": summary.get("total_tests"),
                "tool_backend": metadata.get("tool_backend"),
                "mcp_fallback_used": metadata.get("mcp_fallback_used"),
            }
        )
    return compact


def build_initial_state_from_form(form_data: dict[str, Any]) -> dict[str, Any]:
    """Build LangGraph initial State from dashboard form data."""

    repo_url = str(_get_value(form_data, "repo_url", "") or "").strip()
    repo_path = str(_get_value(form_data, "repo_path", "") or "").strip()
    target_url = str(_get_value(form_data, "target_url", DEFAULT_TARGET_URL) or "").strip()
    focus = str(_get_value(form_data, "focus", "") or "").strip()
    test_types = _get_list(form_data, "test_types") or ["api", "ui", "performance"]

    user_preferences = {
        "test_types": test_types,
        "execution_mode": str(_get_value(form_data, "execution_mode", "sequential") or "sequential"),
        "focus": focus or DEFAULT_FOCUS,
        "rag_top_k": _as_int(_get_value(form_data, "rag_top_k", 8), 8),
        # Dashboard runs are LLM-first by design. If the provider fails, the
        # planner still records a safe deterministic fallback instead of
        # crashing the whole demo workflow.
        "planner_use_llm": True,
        "allow_mutating_api_tests": _as_bool(_get_value(form_data, "allow_mutating_api_tests", False)),
        "skip_ui_testing": _as_bool(_get_value(form_data, "skip_ui_testing", False)),
        "skip_performance_testing": _as_bool(_get_value(form_data, "skip_performance_testing", False)),
        "allow_external_performance_test": _as_bool(_get_value(form_data, "allow_external_performance_test", False)),
        "skip_bug_analysis": _as_bool(_get_value(form_data, "skip_bug_analysis", False)),
        "skip_report": _as_bool(_get_value(form_data, "skip_report", False)),
        "use_mcp_tools": _as_bool(_get_value(form_data, "use_mcp_tools", False)),
    }
    return {
        "repo_url": repo_url,
        "repo_path": repo_path,
        "target_url": target_url or DEFAULT_TARGET_URL,
        "user_preferences": user_preferences,
        "errors": [],
        "agent_logs": [],
    }


def run_workflow_from_form(form_data: dict[str, Any]) -> dict[str, Any]:
    """Run the integrated workflow from dashboard form data."""

    try:
        return run_workflow(build_initial_state_from_form(form_data))
    except Exception as error:
        return {
            "status": "error",
            "error": str(error),
            "errors": [{"agent": "dashboard", "field": "workflow", "message": str(error)}],
        }


def summarize_final_state(final_state: dict[str, Any]) -> dict[str, Any]:
    """Return compact dashboard-safe workflow summary."""

    final_state = final_state or {}
    project_info = final_state.get("project_info") or {}
    api_results = final_state.get("api_results") or {}
    ui_results = final_state.get("ui_results") or {}
    performance_results = final_state.get("performance_results") or {}
    bug_results = final_state.get("bug_results") or {}
    final_results = final_state.get("final_results") or {}
    kpis = final_results.get("kpis") or {}
    errors = final_state.get("errors") or []
    user_preferences = final_state.get("user_preferences") or {}
    tool_backend_metadata: dict[str, Any] = {}
    agent_logs = _compact_agent_logs(final_state.get("agent_logs") or [])
    for log in final_state.get("agent_logs", []) or []:
        if not isinstance(log, dict):
            continue
        agent = log.get("agent")
        metadata = log.get("metadata") or {}
        if agent and (
            "tool_backend" in metadata
            or "mcp_fallback_used" in metadata
        ):
            tool_backend_metadata[str(agent)] = {
                "tool_backend": metadata.get("tool_backend", "local"),
                "mcp_fallback_used": bool(metadata.get("mcp_fallback_used", False)),
            }
    status = final_state.get("status") or final_results.get("status") or ("partial" if errors else "success")
    summary = {
        "run_id": final_state.get("run_id"),
        "status": status,
        "selected_agents": final_state.get("selected_agents", []),
        "planner_model_info": final_state.get("planner_model_info") or {},
        "use_mcp_tools": bool(user_preferences.get("use_mcp_tools", False)),
        "tool_backend_metadata": tool_backend_metadata,
        "mcp_fallback_used": any(
            item.get("mcp_fallback_used") for item in tool_backend_metadata.values()
        ),
        "framework": project_info.get("framework"),
        "target_url": final_state.get("target_url"),
        "rag_query": final_state.get("rag_query"),
        "retrieved_context_count": len(final_state.get("retrieved_context", []) or []),
        "workflow_state_path": safe_artifact_path(final_state.get("workflow_state_path")),
        "project_info_path": safe_artifact_path((final_state.get("output_files") or {}).get("project_info")),
        "test_plan_path": safe_artifact_path(final_state.get("test_plan_path")),
        "api_result_path": safe_artifact_path(final_state.get("api_result_path")),
        "ui_result_path": safe_artifact_path(final_state.get("ui_result_path")),
        "performance_result_path": safe_artifact_path(final_state.get("performance_result_path")),
        "performance_artifact_count": len(final_state.get("performance_artifacts") or []),
        "bug_result_path": safe_artifact_path(final_state.get("bug_result_path")),
        "final_results_path": safe_artifact_path(final_state.get("final_results_path")),
        "report_result_path": safe_artifact_path(final_state.get("report_result_path")),
        "report_html_path": safe_artifact_path(final_state.get("report_html_path")),
        "global_score": kpis.get("global_score", 0.0),
        "api_summary": api_results.get("summary") or final_results.get("api_summary") or {},
        "ui_summary": ui_results.get("summary") or final_results.get("ui_summary") or {},
        "performance_summary": (
            performance_results.get("summary")
            or final_results.get("performance_summary")
            or {}
        ),
        "screenshot_count": kpis.get(
            "screenshot_count",
            len(final_state.get("screenshots") or final_results.get("screenshots") or []),
        ),
        "bug_summary": bug_results.get("summary") or final_results.get("bug_summary") or {},
        "recommendation_count": kpis.get(
            "recommendation_count",
            len(final_state.get("recommendations") or []),
        ),
        "agent_logs": agent_logs,
        "agent_log_count": len(agent_logs),
        "errors": errors,
        "warnings": final_results.get("limitations", []),
    }
    return mask_sensitive_for_display(summary)


def load_report_html_for_display(report_html_path: str | None) -> str:
    """Safely read generated report HTML for embedding in the dashboard."""

    safe_path = safe_artifact_path(report_html_path)
    if not safe_path:
        return ""
    try:
        candidate = Path(safe_path)
        reports_dir = (Path.cwd() / "reports" / "generated").resolve()
        resolved = candidate.resolve()
        resolved.relative_to(reports_dir)
        if not resolved.exists() or not resolved.is_file():
            return ""
        return resolved.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""


def run_and_summarize(form_data: dict[str, Any]) -> dict[str, Any]:
    """Run workflow, summarize final State, and load the generated HTML report."""

    final_state = run_workflow_from_form(form_data)
    if final_state.get("status") == "error":
        return {
            "status": "error",
            "error": final_state.get("error", "Workflow failed."),
            "errors": mask_sensitive_for_display(final_state.get("errors", [])),
        }
    summary = summarize_final_state(final_state)
    return {
        "status": summary.get("status", "success"),
        "summary": summary,
        "report_html": load_report_html_for_display(summary.get("report_html_path")),
        "final_state": {
            "run_id": final_state.get("run_id"),
            "output_files": mask_sensitive_for_display(final_state.get("output_files", {})),
        },
    }
