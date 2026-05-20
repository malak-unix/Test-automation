"""Bug Analysis Agent.

Role in the architecture: read API, UI, and performance results, classify
failures with deterministic rules, assign severity, and generate remediation
recommendations. It analyzes artifacts only; it does not rerun tests.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from test_auto.analysis.bug_rules import analyze_all_results
from test_auto.graph.state import TestAutomationState
from test_auto.shared.schemas import BugAnalysisOutput, BugAnomaly, BugSummary
from test_auto.shared.utils import current_timestamp, generate_run_id
from test_auto.tools.bug_tools import (
    load_api_result_from_run_dir,
    load_bug_context_from_run_dir,
    load_json_file,
    mask_sensitive_values,
    save_bug_result,
)


BUG_ANALYSIS_AGENT_SYSTEM_PROMPT = """
You are the Bug Analysis Agent.
Analyze API, UI, and performance results.
Classify failures into application_bug, security_risk, environment_error, test_data_error, assertion_error, test_script_error, skipped_or_not_executable, or unknown.
Assign severity high, medium, low, or info using evidence only.
Generate concise recommendations.
Do not invent causes.
Return structured JSON.
"""


def _resolve_run_id(
    run_id: str | None = None,
    run_dir: str | None = None,
    api_result_path: str | None = None,
    ui_result_path: str | None = None,
    performance_result_path: str | None = None,
) -> str:
    if run_id:
        return run_id
    if run_dir:
        return Path(run_dir).name
    if api_result_path:
        parent = Path(api_result_path).parent
        if parent.name:
            return parent.name
    if ui_result_path:
        parent = Path(ui_result_path).parent
        if parent.name:
            return parent.name
    if performance_result_path:
        parent = Path(performance_result_path).parent
        if parent.name:
            return parent.name
    return generate_run_id()


def _load_api_results(
    api_results: dict[str, Any] | None = None,
    api_result_path: str | None = None,
    run_dir: str | None = None,
) -> dict[str, Any]:
    if run_dir:
        return load_api_result_from_run_dir(run_dir)
    if api_result_path:
        return load_json_file(api_result_path)
    return api_results or {}


def _load_ui_results(
    ui_results: dict[str, Any] | None = None,
    ui_result_path: str | None = None,
    run_dir: str | None = None,
) -> dict[str, Any]:
    if run_dir:
        return load_json_file(Path(run_dir) / "ui_result.json")
    if ui_result_path:
        return load_json_file(ui_result_path)
    return ui_results or {}


def _load_performance_results(
    performance_results: dict[str, Any] | None = None,
    performance_result_path: str | None = None,
    run_dir: str | None = None,
) -> dict[str, Any]:
    if run_dir:
        return load_json_file(Path(run_dir) / "performance_result.json")
    if performance_result_path:
        return load_json_file(performance_result_path)
    return performance_results or {}


def _resolve_results_dir(
    run_dir: str | None = None,
    api_result_path: str | None = None,
    ui_result_path: str | None = None,
    performance_result_path: str | None = None,
) -> str:
    if run_dir:
        path = Path(run_dir)
        if path.parent.name == "runs":
            return str(path.parent.parent)
    if api_result_path:
        path = Path(api_result_path).parent
        if path.parent.name == "runs":
            return str(path.parent.parent)
    if ui_result_path:
        path = Path(ui_result_path).parent
        if path.parent.name == "runs":
            return str(path.parent.parent)
    if performance_result_path:
        path = Path(performance_result_path).parent
        if path.parent.name == "runs":
            return str(path.parent.parent)
    return "results"


def _build_output(
    status: str,
    duration_seconds: float,
    analysis: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> BugAnalysisOutput:
    return BugAnalysisOutput(
        timestamp=current_timestamp(),
        status=status,
        duration_seconds=duration_seconds,
        summary=BugSummary(**analysis["summary"]),
        anomalies=[BugAnomaly(**item) for item in analysis["anomalies"]],
        recommendations=analysis["recommendations"],
        metadata=metadata or {},
    )


def run_bug_analysis_agent_alone(
    api_results: dict[str, Any] | None = None,
    api_result_path: str | None = None,
    ui_results: dict[str, Any] | None = None,
    ui_result_path: str | None = None,
    performance_results: dict[str, Any] | None = None,
    performance_result_path: str | None = None,
    run_dir: str | None = None,
    run_id: str | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze available test results and save bug_result.json."""

    started = time.perf_counter()
    active_run_id = _resolve_run_id(
        run_id,
        run_dir,
        api_result_path,
        ui_result_path,
        performance_result_path,
    )
    loaded_api_results = _load_api_results(api_results, api_result_path, run_dir)
    loaded_ui_results = _load_ui_results(ui_results, ui_result_path, run_dir)
    loaded_performance_results = _load_performance_results(
        performance_results,
        performance_result_path,
        run_dir,
    )
    if loaded_api_results and (api_result_path or run_dir):
        loaded_api_results.setdefault("metadata", {})
        loaded_api_results["metadata"]["api_result_path"] = (
            api_result_path or str(Path(run_dir or "") / "api_result.json")
        )
    if loaded_ui_results and (ui_result_path or run_dir):
        loaded_ui_results.setdefault("metadata", {})
        loaded_ui_results["metadata"]["ui_result_path"] = (
            ui_result_path or str(Path(run_dir or "") / "ui_result.json")
        )
    if loaded_performance_results and (performance_result_path or run_dir):
        loaded_performance_results.setdefault("metadata", {})
        loaded_performance_results["metadata"]["performance_result_path"] = (
            performance_result_path
            or str(Path(run_dir or "") / "performance_result.json")
        )

    analysis = analyze_all_results(
        api_results=loaded_api_results,
        ui_results=loaded_ui_results,
        perf_results=loaded_performance_results,
        thresholds=thresholds,
    )
    has_api_results = bool(loaded_api_results)
    has_ui_results = bool(loaded_ui_results)
    has_performance_results = bool(loaded_performance_results)
    status = "success" if analysis["summary"]["total_anomalies"] == 0 else "partial"
    if not has_api_results and not has_ui_results and not has_performance_results:
        status = "partial"

    output = _build_output(
        status=status,
        duration_seconds=time.perf_counter() - started,
        analysis=analysis,
        metadata={
            "source": "api_result.json" if (api_result_path or run_dir) else "state",
            "sources": {
                "api": "api_result.json" if (api_result_path or run_dir) else "state",
                "ui": "ui_result.json" if (ui_result_path or run_dir) else "state",
                "performance": (
                    "performance_result.json"
                    if (performance_result_path or run_dir)
                    else "state"
                ),
            },
            "thresholds": thresholds or {},
        },
    )
    output_data = mask_sensitive_values(output.model_dump(mode="json"))
    bug_result_path = save_bug_result(
        active_run_id,
        output_data,
        results_dir=_resolve_results_dir(
            run_dir,
            api_result_path,
            ui_result_path,
            performance_result_path,
        ),
    )
    return {
        "run_id": active_run_id,
        "bug_results": output_data,
        "bug_result_path": bug_result_path,
        "summary": output_data["summary"],
        "recommendations": output_data["recommendations"],
        "errors": [],
        "agent_output": output_data,
    }


def bug_analysis_node(state: TestAutomationState) -> dict[str, Any]:
    """LangGraph node that returns a partial State update for bug analysis."""

    active_run_id = state.get("run_id") or generate_run_id()
    preferences = state.get("user_preferences") or {}
    try:
        result = run_bug_analysis_agent_alone(
            api_results=state.get("api_results"),
            api_result_path=state.get("api_result_path"),
            ui_results=state.get("ui_results"),
            ui_result_path=state.get("ui_result_path"),
            performance_results=state.get("performance_results"),
            performance_result_path=state.get("performance_result_path"),
            run_id=active_run_id,
            thresholds=preferences.get("bug_thresholds"),
        )
        return {
            "run_id": result["run_id"],
            "bug_results": result["bug_results"],
            "bug_result_path": result["bug_result_path"],
            "recommendations": result["recommendations"],
            "agent_logs": [*state.get("agent_logs", []), result["agent_output"]],
            "errors": [*state.get("errors", []), *result.get("errors", [])],
        }
    except Exception as error:
        anomaly = {
            "id": "BUG_ANALYSIS_INTERNAL_001",
            "type": "bug_analysis_internal_error",
            "severity": "low",
            "source_agent": "bug_analysis",
            "classification": "unknown",
            "title": "Bug Analysis Agent failed internally",
            "evidence": {
                "source_agent": "bug_analysis",
                "details": str(error),
            },
            "recommendation": "Inspect Bug Analysis Agent logs before using anomaly output.",
            "confidence": 0.5,
        }
        output = BugAnalysisOutput(
            timestamp=current_timestamp(),
            status="error",
            duration_seconds=0.0,
            summary=BugSummary(
                total_anomalies=1,
                low=1,
                by_classification={"unknown": 1},
            ),
            anomalies=[BugAnomaly(**anomaly)],
            recommendations=[
                {
                    "priority": "low",
                    "title": "Inspect Bug Analysis Agent",
                    "action": "Review the internal error before interpreting bug analysis.",
                    "related_anomaly_ids": ["BUG_ANALYSIS_INTERNAL_001"],
                }
            ],
            metadata={},
        )
        output_data = mask_sensitive_values(output.model_dump(mode="json"))
        path = save_bug_result(active_run_id, output_data)
        return {
            "run_id": active_run_id,
            "bug_results": output_data,
            "bug_result_path": path,
            "recommendations": output_data["recommendations"],
            "agent_logs": [*state.get("agent_logs", []), output_data],
            "errors": [
                *state.get("errors", []),
                {"agent": "bug_analysis", "field": "internal", "message": str(error)},
            ],
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Bug Analysis Agent alone.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-dir", default=None)
    source.add_argument("--api-result", default=None)
    return parser.parse_args()


def _compact_cli_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": result.get("run_id"),
        "summary": result.get("summary"),
        "bug_result_path": result.get("bug_result_path"),
        "recommendations_count": len(result.get("recommendations", [])),
    }


def main() -> None:
    """CLI entry point for standalone bug analysis."""

    args = _parse_args()
    if args.run_dir:
        context = load_bug_context_from_run_dir(args.run_dir)
        result = run_bug_analysis_agent_alone(
            api_results=context.get("api_results"),
            run_dir=args.run_dir,
        )
    else:
        result = run_bug_analysis_agent_alone(api_result_path=args.api_result)
    print(json.dumps(_compact_cli_result(result), indent=2))


if __name__ == "__main__":
    main()
