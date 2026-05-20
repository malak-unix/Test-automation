"""Local tools for deterministic bug analysis."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from test_auto.shared.utils import ensure_directory, json_safe, write_json_file


MASK = "***MASKED***"
SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "auth_token",
    "cookie",
    "password",
    "refresh_token",
    "secret",
    "set-cookie",
    "token",
    "x-api-key",
}
TOKEN_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"(token|api_key|secret|authorization)=([^&\s]+)", re.IGNORECASE),
]


def load_json_file(path: str | Path) -> dict[str, Any]:
    """Load a JSON file safely, returning an empty dict on failure."""

    try:
        file_path = Path(path)
        if not file_path.exists():
            return {}
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_api_result_from_run_dir(run_dir: str | Path) -> dict[str, Any]:
    """Load api_result.json from a previous run directory."""

    return load_json_file(Path(run_dir) / "api_result.json")


def _mask_string(value: str) -> str:
    masked = value
    for pattern in TOKEN_PATTERNS:
        masked = pattern.sub(lambda match: match.group(0).split()[0] + f" {MASK}" if match.group(0).lower().startswith("bearer") else f"{match.group(1)}={MASK}", masked)
    return masked


def mask_sensitive_values(data: Any) -> Any:
    """Recursively mask token-like or secret-like values."""

    if isinstance(data, dict):
        masked: dict[str, Any] = {}
        for key, value in data.items():
            key_string = str(key)
            if key_string.lower().replace("_", "-") in SENSITIVE_KEYS:
                masked[key_string] = MASK
            else:
                masked[key_string] = mask_sensitive_values(value)
        return masked
    if isinstance(data, list):
        return [mask_sensitive_values(item) for item in data]
    if isinstance(data, tuple):
        return [mask_sensitive_values(item) for item in data]
    if isinstance(data, str):
        return _mask_string(data)
    return data


def save_bug_result(
    run_id: str,
    bug_output: dict[str, Any],
    results_dir: str = "results",
) -> str:
    """Save results/runs/<run_id>/bug_result.json."""

    run_dir = ensure_directory(Path(results_dir) / "runs" / run_id)
    path = write_json_file(
        run_dir / "bug_result.json",
        json_safe(mask_sensitive_values(bug_output)),
    )
    return str(path)


def load_bug_context_from_run_dir(run_dir: str | Path) -> dict[str, Any]:
    """Load compact bug-analysis context from a previous workflow run."""

    base = Path(run_dir)
    workflow_state = load_json_file(base / "workflow_state.json")
    project_info = load_json_file(base / "project_info.json")
    api_results = load_api_result_from_run_dir(base)
    return mask_sensitive_values(
        {
            "run_id": base.name,
            "api_results": api_results,
            "project_info": project_info or workflow_state.get("project_info", {}),
            "workflow_state": workflow_state,
        }
    )
