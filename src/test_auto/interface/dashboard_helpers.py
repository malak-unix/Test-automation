"""Dashboard helpers for safe artifact discovery and display."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from test_auto.shared.utils import json_safe
from test_auto.tools.bug_tools import mask_sensitive_values


def get_results_base_dir() -> Path:
    """Return the workflow run directory."""

    return Path("results") / "runs"


def mask_sensitive_for_display(data: Any) -> Any:
    """Mask sensitive values before rendering dashboard content."""

    return mask_sensitive_values(json_safe(data))


def _safe_load_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _is_safe_run_id(run_id: str) -> bool:
    if not run_id or any(part in run_id for part in ("/", "\\", "..")):
        return False
    return run_id == Path(run_id).name


def safe_artifact_path(path: str | None) -> str:
    """Return a display path only for local project artifacts."""

    if not path:
        return ""
    try:
        candidate = Path(path)
        normalized = str(candidate).replace("\\", "/")
        allowed_prefixes = (
            "results/runs/",
            "reports/generated/",
        )
        if candidate.is_absolute():
            project_root = Path.cwd().resolve()
            candidate.resolve().relative_to(project_root)
            normalized = str(candidate.resolve().relative_to(project_root)).replace("\\", "/")
        if normalized.startswith(allowed_prefixes):
            return str(candidate)
    except (OSError, ValueError):
        return ""
    return ""


def get_latest_run_id() -> str | None:
    """Return the latest run id recorded by Report Agent, if present."""

    path = Path("results") / "latest_run.txt"
    try:
        run_id = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return run_id if _is_safe_run_id(run_id) else None


def _summary_from_final_results(run_id: str, final_results: dict[str, Any]) -> dict[str, Any]:
    kpis = final_results.get("kpis") or {}
    artifact_paths = final_results.get("artifact_paths") or {}
    return {
        "run_id": run_id,
        "modified_at": "",
        "workflow_state_exists": False,
        "final_results_exists": bool(final_results),
        "report_html_path": safe_artifact_path(artifact_paths.get("report_html_path")),
        "global_score": kpis.get("global_score", 0.0),
        "api_pass_rate": kpis.get("pass_rate", 0.0),
        "ui_pass_rate": kpis.get("ui_pass_rate", 0.0),
        "performance_failure_rate": kpis.get("overall_failure_rate", 0.0),
        "screenshot_count": kpis.get("screenshot_count", 0),
        "total_anomalies": kpis.get("total_anomalies", 0),
    }


def list_recent_runs(limit: int = 10) -> list[dict[str, Any]]:
    """List recent result runs with compact report metrics."""

    base_dir = get_results_base_dir()
    if not base_dir.exists():
        return []

    run_dirs = [path for path in base_dir.iterdir() if path.is_dir()]
    run_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    recent: list[dict[str, Any]] = []
    for run_dir in run_dirs[:limit]:
        final_results = _safe_load_json(run_dir / "final_results.json")
        summary = _summary_from_final_results(run_dir.name, final_results)
        summary["modified_at"] = datetime.fromtimestamp(
            run_dir.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat()
        summary["workflow_state_exists"] = (run_dir / "workflow_state.json").exists()
        summary["final_results_exists"] = (run_dir / "final_results.json").exists()
        if not summary["report_html_path"]:
            fallback_html = Path("reports") / "generated" / f"report_{run_dir.name}.html"
            summary["report_html_path"] = safe_artifact_path(str(fallback_html))
        recent.append(mask_sensitive_for_display(summary))
    return recent


def load_run_summary(run_id: str) -> dict[str, Any]:
    """Load a compact summary for a previous run."""

    if not _is_safe_run_id(run_id):
        return {}
    run_dir = get_results_base_dir() / run_id
    if not run_dir.exists():
        return {}

    final_results = _safe_load_json(run_dir / "final_results.json")
    if final_results:
        kpis = final_results.get("kpis") or {}
        report_html_path = safe_artifact_path(
            (final_results.get("artifact_paths") or {}).get("report_html_path")
        )
        if not report_html_path:
            report_html_path = safe_artifact_path(
                str(Path("reports") / "generated" / f"report_{run_id}.html")
            )
        summary = _summary_from_final_results(run_id, final_results)
        summary.update(
            {
                "status": final_results.get("status", "partial"),
                "framework": (final_results.get("project_info") or {}).get("framework"),
                "target_url": final_results.get("target_url"),
                "api_summary": final_results.get("api_summary") or {},
                "ui_summary": final_results.get("ui_summary") or {},
                "performance_summary": final_results.get("performance_summary") or {},
                "screenshot_count": kpis.get("screenshot_count", 0),
                "bug_summary": final_results.get("bug_summary") or {},
                "report_html_path": report_html_path,
                "final_results_path": safe_artifact_path(str(run_dir / "final_results.json")),
                "report_result_path": safe_artifact_path(str(run_dir / "report_result.json")),
                "workflow_state_path": safe_artifact_path(str(run_dir / "workflow_state.json")),
                "errors": [],
                "warnings": final_results.get("limitations") or [],
            }
        )
        return mask_sensitive_for_display(summary)

    workflow_state = _safe_load_json(run_dir / "workflow_state.json")
    if not workflow_state:
        return {}
    from test_auto.interface.run_service import summarize_final_state

    return summarize_final_state(workflow_state)
