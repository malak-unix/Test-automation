"""Load and merge existing run artifacts for Report Agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_auto.shared.utils import generate_run_id, json_safe
from test_auto.tools.bug_tools import mask_sensitive_values


def _safe_load_any_json(path: str | Path) -> Any:
    """Return decoded JSON content or an empty dict when unavailable."""

    try:
        json_path = Path(path)
        if not json_path.exists():
            return {}
        return json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def safe_load_json(path: str | Path) -> dict[str, Any]:
    """Load a JSON object safely from disk."""

    data = _safe_load_any_json(path)
    return data if isinstance(data, dict) else {}


def infer_run_id_from_run_dir(run_dir: str | Path) -> str:
    """Infer run_id from a results/runs/<run_id> directory."""

    name = Path(run_dir).name
    return name if name else generate_run_id()


def _existing_path(path: Path) -> str | None:
    return str(path) if path.exists() else None


def load_run_artifacts(run_dir: str | Path) -> dict[str, Any]:
    """Load known artifacts from a previous workflow run directory."""

    directory = Path(run_dir)
    retrieved_context = _safe_load_any_json(directory / "retrieved_context.json")
    if not isinstance(retrieved_context, list):
        retrieved_context = []

    artifact_paths = {
        "workflow_state_path": _existing_path(directory / "workflow_state.json"),
        "project_info_path": _existing_path(directory / "project_info.json"),
        "test_plan_path": _existing_path(directory / "test_plan.json"),
        "api_result_path": _existing_path(directory / "api_result.json"),
        "ui_result_path": _existing_path(directory / "ui_result.json"),
        "performance_result_path": _existing_path(directory / "performance_result.json"),
        "bug_result_path": _existing_path(directory / "bug_result.json"),
    }
    return mask_sensitive_report_data(
        {
            "run_id": infer_run_id_from_run_dir(directory),
            "workflow_state": safe_load_json(directory / "workflow_state.json"),
            "project_info": safe_load_json(directory / "project_info.json"),
            "test_plan": safe_load_json(directory / "test_plan.json"),
            "api_results": safe_load_json(directory / "api_result.json"),
            "ui_results": safe_load_json(directory / "ui_result.json"),
            "performance_results": safe_load_json(directory / "performance_result.json"),
            "bug_results": safe_load_json(directory / "bug_result.json"),
            "screenshots": (safe_load_json(directory / "ui_result.json").get("screenshots") or []),
            "retrieved_context": retrieved_context,
            "artifact_paths": artifact_paths,
        }
    )


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def merge_state_and_artifacts(
    state: dict[str, Any] | None,
    artifacts: dict[str, Any] | None,
) -> dict[str, Any]:
    """Prefer explicit State values and use loaded artifacts as fallback."""

    state = state or {}
    artifacts = artifacts or {}
    workflow_state = artifacts.get("workflow_state") or {}
    bug_results = _first_present(
        state.get("bug_results"),
        artifacts.get("bug_results"),
        workflow_state.get("bug_results"),
        {},
    )
    ui_results = _first_present(
        state.get("ui_results"),
        artifacts.get("ui_results"),
        workflow_state.get("ui_results"),
        {},
    )
    performance_results = _first_present(
        state.get("performance_results"),
        artifacts.get("performance_results"),
        workflow_state.get("performance_results"),
        {},
    )
    recommendations = _first_present(
        state.get("recommendations"),
        (bug_results or {}).get("recommendations") if isinstance(bug_results, dict) else None,
        workflow_state.get("recommendations"),
        [],
    )
    artifact_paths = {
        **(artifacts.get("artifact_paths") or {}),
        "test_plan_path": _first_present(
            state.get("test_plan_path"),
            (artifacts.get("artifact_paths") or {}).get("test_plan_path"),
        ),
        "api_result_path": _first_present(
            state.get("api_result_path"),
            (artifacts.get("artifact_paths") or {}).get("api_result_path"),
        ),
        "ui_result_path": _first_present(
            state.get("ui_result_path"),
            (artifacts.get("artifact_paths") or {}).get("ui_result_path"),
        ),
        "performance_result_path": _first_present(
            state.get("performance_result_path"),
            (artifacts.get("artifact_paths") or {}).get("performance_result_path"),
        ),
        "bug_result_path": _first_present(
            state.get("bug_result_path"),
            (artifacts.get("artifact_paths") or {}).get("bug_result_path"),
        ),
        "workflow_state_path": _first_present(
            state.get("workflow_state_path"),
            (artifacts.get("artifact_paths") or {}).get("workflow_state_path"),
        ),
    }
    context = {
        "run_id": _first_present(state.get("run_id"), artifacts.get("run_id"), workflow_state.get("run_id")),
        "repo_url": _first_present(state.get("repo_url"), workflow_state.get("repo_url")),
        "target_url": _first_present(state.get("target_url"), workflow_state.get("target_url")),
        "project_info": _first_present(
            state.get("project_info"),
            artifacts.get("project_info"),
            workflow_state.get("project_info"),
            {},
        ),
        "test_plan": _first_present(
            state.get("test_plan"),
            artifacts.get("test_plan"),
            workflow_state.get("test_plan"),
            {},
        ),
        "api_results": _first_present(
            state.get("api_results"),
            artifacts.get("api_results"),
            workflow_state.get("api_results"),
            {},
        ),
        "ui_results": ui_results or {},
        "performance_results": performance_results or {},
        "performance_artifacts": _first_present(
            state.get("performance_artifacts"),
            (performance_results or {}).get("artifacts")
            if isinstance(performance_results, dict)
            else None,
            workflow_state.get("performance_artifacts"),
            [],
        ),
        "bug_results": bug_results or {},
        "screenshots": _first_present(
            state.get("screenshots"),
            (ui_results or {}).get("screenshots") if isinstance(ui_results, dict) else None,
            artifacts.get("screenshots"),
            workflow_state.get("screenshots"),
            [],
        ),
        "retrieved_context": _first_present(
            state.get("retrieved_context"),
            artifacts.get("retrieved_context"),
            workflow_state.get("retrieved_context"),
            [],
        ),
        "recommendations": recommendations or [],
        "user_preferences": _first_present(
            state.get("user_preferences"),
            workflow_state.get("user_preferences"),
            {},
        ),
        "artifact_paths": artifact_paths,
        "workflow_state": workflow_state,
    }
    return mask_sensitive_report_data(context)


def mask_sensitive_report_data(data: Any) -> Any:
    """Mask secrets and convert values into JSON-safe report data."""

    return mask_sensitive_values(json_safe(data))
