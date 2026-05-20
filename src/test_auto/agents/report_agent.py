"""Report Agent.

Role in the architecture: merge run artifacts and final State into
final_results.json, report_result.json, dashboard_payload, and an HTML report.
It masks sensitive values and stores only reportable summaries.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from test_auto.graph.state import TestAutomationState
from test_auto.mcp.tool_router import build_mcp_agent_log, call_mcp_or_local, should_use_mcp
from test_auto.reporting.artifact_loader import (
    load_run_artifacts,
    mask_sensitive_report_data,
    merge_state_and_artifacts,
    safe_load_json,
)
from test_auto.reporting.html_renderer import render_and_save_report
from test_auto.reporting.report_builder import (
    build_dashboard_payload,
    build_final_results,
)
from test_auto.shared.schemas import ReportAgentOutput
from test_auto.shared.utils import current_timestamp, generate_run_id
from test_auto.tools.report_tools import (
    save_final_results,
    save_report_result,
    update_latest_run,
)


REPORT_AGENT_SYSTEM_PROMPT = """
You are the Report Agent.
Aggregate all agent outputs into a clear testing report.
Show KPIs, test results, evidence, anomalies, and recommendations.
Do not hide failures.
Distinguish environment errors, test-data errors, security risks, and application bugs.
Return final_results and report_html_path.
"""


def _expected_final_results_path(run_id: str, results_dir: str) -> str:
    return str(Path(results_dir) / "runs" / run_id / "final_results.json")


def _expected_report_result_path(run_id: str, results_dir: str) -> str:
    return str(Path(results_dir) / "runs" / run_id / "report_result.json")


def _expected_report_html_path(run_id: str) -> str:
    return str(Path("reports") / "generated" / f"report_{run_id}.html")


def _missing_sections(final_results: dict[str, Any]) -> list[str]:
    return [
        section.get("title", "Unknown")
        for section in final_results.get("sections", [])
        if section.get("status") == "missing"
    ]


def _output_status(final_results: dict[str, Any]) -> str:
    if final_results.get("status") == "error":
        return "error"
    if _missing_sections(final_results):
        return "partial"
    return final_results.get("status") or "success"


def _local_render_report_payload(final_results: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "report_html_path": render_and_save_report(final_results),
        "error": None,
    }


def run_report_agent_alone(
    run_dir: str | None = None,
    run_id: str | None = None,
    context: dict[str, Any] | None = None,
    results_dir: str = "results",
) -> dict[str, Any]:
    """Aggregate run artifacts and save final JSON and HTML report outputs."""

    started = time.perf_counter()
    artifacts = load_run_artifacts(run_dir) if run_dir else {}
    merged_context = merge_state_and_artifacts(context or {}, artifacts)
    active_run_id = run_id or merged_context.get("run_id") or generate_run_id()
    merged_context["run_id"] = active_run_id
    user_preferences = merged_context.get("user_preferences") or {}
    mcp_events: list[dict[str, Any]] = []

    final_results = build_final_results(merged_context)
    final_results.setdefault("artifact_paths", {})
    final_results["artifact_paths"].update(
        {
            "final_results_path": _expected_final_results_path(active_run_id, results_dir),
            "report_result_path": _expected_report_result_path(active_run_id, results_dir),
            "report_html_path": _expected_report_html_path(active_run_id),
        }
    )
    final_results = mask_sensitive_report_data(final_results)
    dashboard_payload = build_dashboard_payload(final_results)

    final_results_path = save_final_results(active_run_id, final_results, results_dir=results_dir)
    if should_use_mcp(user_preferences):
        routed = call_mcp_or_local(
            tool_name="generate_html_report_tool",
            mcp_args={
                "final_results_path": final_results_path,
                "output_path": _expected_report_html_path(active_run_id),
            },
            local_callable=_local_render_report_payload,
            local_args={"final_results": final_results},
            user_preferences=user_preferences,
        )
        render_result = routed.get("result") or {}
        report_html_path = (
            render_result.get("report_html_path")
            if isinstance(render_result, dict)
            else str(render_result)
        )
        mcp_events.append(
            build_mcp_agent_log(
                "generate_html_report_tool",
                used_mcp=routed.get("used_mcp", False),
                fallback_used=routed.get("fallback_used", False),
                error=routed.get("mcp_error") or routed.get("error"),
            )
        )
    else:
        report_html_path = render_and_save_report(final_results)
    tool_backend = (
        "mcp"
        if any(event.get("used_mcp") for event in mcp_events)
        and not any(event.get("fallback_used") for event in mcp_events)
        else "mixed"
        if any(event.get("fallback_used") for event in mcp_events)
        else "local"
    )
    mcp_fallback_used = any(event.get("fallback_used") for event in mcp_events)
    final_results["artifact_paths"]["report_html_path"] = report_html_path
    dashboard_payload["report_html_path"] = report_html_path

    output = ReportAgentOutput(
        timestamp=current_timestamp(),
        status=_output_status(final_results),
        duration_seconds=time.perf_counter() - started,
        final_results=final_results,
        report_html_path=report_html_path,
        dashboard_payload=dashboard_payload,
        anomalies=[],
        metadata={
            "source": "run_dir" if run_dir else "state",
            "missing_sections": _missing_sections(final_results),
            "tool_backend": tool_backend,
            "mcp_fallback_used": mcp_fallback_used,
            "mcp_events": mcp_events,
        },
    )
    report_result = mask_sensitive_report_data(output.model_dump(mode="json"))
    report_result_path = save_report_result(active_run_id, report_result, results_dir=results_dir)
    update_latest_run(active_run_id, results_dir=results_dir)

    final_results["artifact_paths"]["final_results_path"] = final_results_path
    final_results["artifact_paths"]["report_result_path"] = report_result_path
    final_results_path = save_final_results(active_run_id, final_results, results_dir=results_dir)
    report_result["final_results"]["artifact_paths"]["final_results_path"] = final_results_path
    report_result["final_results"]["artifact_paths"]["report_result_path"] = report_result_path
    report_result["report_html_path"] = report_html_path
    report_result_path = save_report_result(active_run_id, report_result, results_dir=results_dir)

    return {
        "run_id": active_run_id,
        "final_results": final_results,
        "final_results_path": final_results_path,
        "report_result": report_result,
        "report_result_path": report_result_path,
        "report_html_path": report_html_path,
        "dashboard_payload": dashboard_payload,
        "summary": final_results.get("kpis", {}),
        "errors": [],
        "agent_output": report_result,
    }


def report_node(state: TestAutomationState) -> dict[str, Any]:
    """LangGraph node that returns a partial State update for report generation."""

    active_run_id = state.get("run_id") or generate_run_id()
    try:
        result = run_report_agent_alone(
            run_id=active_run_id,
            context=dict(state),
        )
        return {
            "run_id": result["run_id"],
            "final_results": result["final_results"],
            "final_results_path": result["final_results_path"],
            "report_result": result["report_result"],
            "report_result_path": result["report_result_path"],
            "report_html_path": result["report_html_path"],
            "dashboard_payload": result["dashboard_payload"],
            "agent_logs": [*state.get("agent_logs", []), result["agent_output"]],
            "errors": [*state.get("errors", []), *result.get("errors", [])],
        }
    except Exception as error:
        fallback = run_report_agent_alone(
            run_id=active_run_id,
            context={
                "run_id": active_run_id,
                "user_preferences": state.get("user_preferences") or {},
            },
        )
        return {
            "run_id": active_run_id,
            "final_results": fallback["final_results"],
            "final_results_path": fallback["final_results_path"],
            "report_result": fallback["report_result"],
            "report_result_path": fallback["report_result_path"],
            "report_html_path": fallback["report_html_path"],
            "dashboard_payload": fallback["dashboard_payload"],
            "agent_logs": [*state.get("agent_logs", []), fallback["agent_output"]],
            "errors": [
                *state.get("errors", []),
                {"agent": "report", "field": "internal", "message": str(error)},
            ],
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Report Agent alone.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-dir", default=None)
    source.add_argument("--context-json", default=None)
    return parser.parse_args()


def _compact_cli_result(result: dict[str, Any]) -> dict[str, Any]:
    final_results = result.get("final_results") or {}
    kpis = final_results.get("kpis") or {}
    return {
        "run_id": result.get("run_id"),
        "global_score": kpis.get("global_score"),
        "final_results_path": result.get("final_results_path"),
        "report_result_path": result.get("report_result_path"),
        "report_html_path": result.get("report_html_path"),
        "recommendation_count": kpis.get("recommendation_count", 0),
        "missing_sections": _missing_sections(final_results),
    }


def main() -> None:
    """CLI entry point for standalone report generation."""

    args = _parse_args()
    if args.run_dir:
        result = run_report_agent_alone(run_dir=args.run_dir)
    else:
        result = run_report_agent_alone(context=safe_load_json(args.context_json))
    print(json.dumps(_compact_cli_result(result), indent=2))


if __name__ == "__main__":
    main()
