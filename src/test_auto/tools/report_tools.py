"""Local tools used by the Report Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from test_auto.reporting.artifact_loader import (
    load_run_artifacts,
    mask_sensitive_report_data,
)
from test_auto.shared.utils import ensure_directory, write_json_file


def save_final_results(
    run_id: str,
    final_results: dict[str, Any],
    results_dir: str = "results",
) -> str:
    """Save results/runs/<run_id>/final_results.json."""

    run_dir = ensure_directory(Path(results_dir) / "runs" / run_id)
    path = run_dir / "final_results.json"
    write_json_file(path, mask_sensitive_report_data(final_results))
    return str(path)


def save_report_result(
    run_id: str,
    report_output: dict[str, Any],
    results_dir: str = "results",
) -> str:
    """Save results/runs/<run_id>/report_result.json."""

    run_dir = ensure_directory(Path(results_dir) / "runs" / run_id)
    path = run_dir / "report_result.json"
    write_json_file(path, mask_sensitive_report_data(report_output))
    return str(path)


def update_latest_run(run_id: str, results_dir: str = "results") -> str:
    """Write results/latest_run.txt for later dashboard discovery."""

    results_path = ensure_directory(results_dir)
    path = results_path / "latest_run.txt"
    path.write_text(run_id, encoding="utf-8")
    return str(path)


def load_report_context_from_run_dir(run_dir: str) -> dict[str, Any]:
    """Load report context from a previous run directory."""

    return load_run_artifacts(run_dir)


def open_report_hint(report_html_path: str) -> str:
    """Return a human-readable hint without opening a browser."""

    return f"Open this file in your browser: {report_html_path}"
