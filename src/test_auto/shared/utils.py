"""Small reusable utilities for the test automation project."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

SENSITIVE_JSON_KEYS = {
    "api_key",
    "authorization",
    "auth_token",
    "cookie",
    "password",
    "refresh_token",
    "secret",
    "set_cookie",
    "set-cookie",
    "token",
    "x_api_key",
    "x-api-key",
}
MASKED_VALUE = "***MASKED***"


def current_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def generate_run_id(prefix: str = "run") -> str:
    """Generate a filesystem-friendly run identifier."""

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


def validate_url(value: str) -> bool:
    """Return True when a value looks like an HTTP or HTTPS URL."""

    if not value or not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def ensure_directory(path: str | Path) -> Path:
    """Create a directory if needed and return it as a Path."""

    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_json_file(path: str | Path, data: dict[str, Any]) -> Path:
    """Write a JSON file with stable formatting."""

    json_path = Path(path)
    ensure_directory(json_path.parent)
    with json_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)
        file.write("\n")
    return json_path


def json_safe(value: Any) -> Any:
    """Convert common Python/Pydantic objects into JSON-safe values."""

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            string_key = str(key)
            normalized_key = string_key.lower().replace("-", "_")
            if normalized_key in SENSITIVE_JSON_KEYS:
                safe[string_key] = MASKED_VALUE
            else:
                safe[string_key] = json_safe(item)
        return safe
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def save_workflow_state(
    state: dict[str, Any],
    run_id: str,
    results_dir: str = "results",
) -> str:
    """Save final workflow State under results/runs/<run_id>/workflow_state.json."""

    run_dir = ensure_directory(Path(results_dir) / "runs" / run_id)
    workflow_state_path = run_dir / "workflow_state.json"
    write_json_file(workflow_state_path, json_safe(state))
    return str(workflow_state_path)
