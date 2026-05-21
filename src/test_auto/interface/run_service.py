"""Service layer that connects Flask forms to the LangGraph workflow."""

from __future__ import annotations

from threading import Lock, Thread
from pathlib import Path
from typing import Any

from test_auto.graph.workflow import run_workflow
from test_auto.interface.dashboard_helpers import (
    mask_sensitive_for_display,
    safe_artifact_path,
)
from test_auto.shared.utils import json_safe
from test_auto.shared.utils import current_timestamp, generate_run_id


DEFAULT_REPO_URL = "https://github.com/Vitaee/DjangoRestAPI"
DEFAULT_TARGET_URL = "http://localhost:8000"
DEFAULT_FOCUS = "JWT authentication todo CRUD API tests"
_JOB_LOCK = Lock()
_WORKFLOW_JOBS: dict[str, dict[str, Any]] = {}


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


def _copy_form_data(form_data: Any) -> dict[str, Any]:
    """Copy Flask form data before running the workflow in a background thread."""

    if not hasattr(form_data, "keys"):
        return dict(form_data or {})
    copied: dict[str, Any] = {}
    for key in form_data.keys():
        values = form_data.getlist(key) if hasattr(form_data, "getlist") else [form_data.get(key)]
        copied[key] = values if key == "test_types" or len(values) > 1 else values[0]
    return copied


def _update_job(job_id: str, updates: dict[str, Any]) -> None:
    with _JOB_LOCK:
        job = _WORKFLOW_JOBS.setdefault(job_id, {})
        job.update(mask_sensitive_for_display(updates))


def _append_job_event(job_id: str, event: dict[str, Any]) -> None:
    safe_event = mask_sensitive_for_display(
        {
            "timestamp": current_timestamp(),
            **event,
        }
    )
    with _JOB_LOCK:
        job = _WORKFLOW_JOBS.setdefault(job_id, {})
        events = job.setdefault("events", [])
        events.append(safe_event)
        job["last_event"] = safe_event


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


def _compact_rag_context(chunks: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks or [], start=1):
        if not isinstance(chunk, dict):
            continue
        compact.append(
            {
                "index": index,
                "source": chunk.get("source") or chunk.get("path") or chunk.get("file_path") or "unknown",
                "score": chunk.get("score") or chunk.get("similarity"),
                "preview": str(
                    chunk.get("text")
                    or chunk.get("content")
                    or chunk.get("preview")
                    or ""
                )[:420],
            }
        )
    return compact


def _compact_test_plan_trace(test_plan: dict[str, Any] | None) -> dict[str, Any]:
    plan = test_plan or {}
    return {
        "scope": plan.get("scope") or "Not available",
        "reasoning_summary": plan.get("reasoning_summary") or "",
        "api_tests": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "method": item.get("method"),
                "endpoint": item.get("endpoint"),
                "expected_status": item.get("expected_status"),
            }
            for item in plan.get("api_tests", [])[:8]
            if isinstance(item, dict)
        ],
        "ui_tests": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "flow": item.get("flow"),
                "expected_result": item.get("expected_result"),
            }
            for item in plan.get("ui_tests", [])[:6]
            if isinstance(item, dict)
        ],
        "performance_tests": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "method": item.get("method"),
                "endpoint": item.get("endpoint"),
                "users": item.get("users"),
                "duration_seconds": item.get("duration_seconds"),
            }
            for item in plan.get("performance_tests", [])[:6]
            if isinstance(item, dict)
        ],
    }


def _compact_mcp_events(agent_logs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for log in agent_logs or []:
        if not isinstance(log, dict):
            continue
        metadata = log.get("metadata") or {}
        for event in metadata.get("mcp_events") or []:
            if not isinstance(event, dict):
                continue
            events.append(
                {
                    "agent": log.get("agent"),
                    "tool": event.get("tool_name") or event.get("tool"),
                    "used_mcp": bool(event.get("used_mcp")),
                    "fallback_used": bool(event.get("fallback_used")),
                    "error": event.get("error"),
                }
            )
    return events


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
        # Dashboard runs use MCP by default because MCP is part of the final
        # project architecture. Agents still keep their local fallback so a
        # missing MCP server does not break the demo.
        "use_mcp_tools": _as_bool(_get_value(form_data, "use_mcp_tools", True)),
    }
    return {
        "repo_url": repo_url,
        "repo_path": repo_path,
        "target_url": target_url or DEFAULT_TARGET_URL,
        "user_preferences": user_preferences,
        "errors": [],
        "agent_logs": [],
    }


def start_workflow_job(form_data: Any) -> str:
    """Start a dashboard workflow job and return its in-memory job id."""

    job_id = generate_run_id("dashboard_job")
    copied_form = _copy_form_data(form_data)
    _update_job(
        job_id,
        {
            "job_id": job_id,
            "status": "queued",
            "events": [],
            "created_at": current_timestamp(),
            "run_id": None,
            "result_url": None,
            "error": None,
        },
    )

    def worker() -> None:
        _update_job(job_id, {"status": "running", "started_at": current_timestamp()})
        _append_job_event(
            job_id,
            {
                "agent": "dashboard",
                "status": "running",
                "message": "Workflow submitted from dashboard.",
            },
        )
        try:
            initial_state = build_initial_state_from_form(copied_form)
            final_state = run_workflow(
                initial_state,
                progress_callback=lambda event: _append_job_event(job_id, event),
            )
            summary = summarize_final_state(final_state)
            _append_job_event(
                job_id,
                {
                    "agent": "dashboard",
                    "status": "success",
                    "message": "Workflow completed and report artifacts were saved.",
                },
            )
            _update_job(
                job_id,
                {
                    "status": "completed",
                    "completed_at": current_timestamp(),
                    "run_id": final_state.get("run_id"),
                    "result_url": f"/runs/{final_state.get('run_id')}",
                    "summary": summary,
                },
            )
        except Exception as error:
            _append_job_event(
                job_id,
                {
                    "agent": "dashboard",
                    "status": "error",
                    "message": f"Workflow failed safely: {error.__class__.__name__}",
                },
            )
            _update_job(
                job_id,
                {
                    "status": "error",
                    "completed_at": current_timestamp(),
                    "error": str(error),
                },
            )

    Thread(target=worker, daemon=True).start()
    return job_id


def get_workflow_job(job_id: str) -> dict[str, Any]:
    """Return a dashboard-safe snapshot of one background workflow job."""

    with _JOB_LOCK:
        job = dict(_WORKFLOW_JOBS.get(job_id) or {})
        if "events" in job:
            job["events"] = list(job["events"])
    if not job:
        return {"job_id": job_id, "status": "not_found", "events": []}
    return mask_sensitive_for_display(json_safe(job))


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
        "rag_trace": _compact_rag_context(final_state.get("retrieved_context") or []),
        "test_plan_trace": _compact_test_plan_trace(final_state.get("test_plan") or {}),
        "mcp_events": _compact_mcp_events(final_state.get("agent_logs") or []),
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
