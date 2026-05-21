"""Build final report data structures from agent outputs."""

from __future__ import annotations

from typing import Any

from test_auto.reporting.artifact_loader import mask_sensitive_report_data
from test_auto.reporting.kpi_calculator import compute_report_kpis
from test_auto.shared.schemas import (
    FinalResults,
    ReportArtifactPaths,
    ReportKPIs,
    ReportSection,
)
from test_auto.shared.utils import current_timestamp, generate_run_id


def _compact_api_test(test: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": test.get("id"),
        "name": test.get("name"),
        "method": test.get("method"),
        "endpoint": test.get("endpoint"),
        "status": test.get("status"),
        "expected_status": test.get("expected_status"),
        "actual_status": test.get("actual_status"),
        "duration_ms": test.get("duration_ms"),
        "details": test.get("details"),
    }


def _compact_ui_test(test: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": test.get("id"),
        "name": test.get("name"),
        "flow": test.get("flow"),
        "status": test.get("status"),
        "target_path": test.get("target_path"),
        "target_url": test.get("target_url"),
        "duration_ms": test.get("duration_ms"),
        "details": test.get("details"),
    }


def _compact_performance_test(test: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": test.get("id"),
        "name": test.get("name"),
        "endpoint": test.get("endpoint"),
        "method": test.get("method"),
        "users": test.get("users"),
        "duration_seconds": test.get("duration_seconds"),
        "total_requests": test.get("total_requests"),
        "failures": test.get("failures"),
        "failure_rate": test.get("failure_rate"),
        "average_response_time_ms": test.get("average_response_time_ms"),
        "p95_response_time_ms": test.get("p95_response_time_ms"),
        "status": test.get("status"),
        "details": test.get("details"),
    }


def summarize_test_plan(test_plan: dict[str, Any]) -> dict[str, Any]:
    """Summarize planned tests and known planning gaps."""

    test_plan = test_plan or {}
    return {
        "api_tests": len(test_plan.get("api_tests") or []),
        "ui_tests": len(test_plan.get("ui_tests") or []),
        "performance_tests": len(test_plan.get("performance_tests") or []),
        "scope": test_plan.get("scope") or test_plan.get("objective") or "Not specified",
        "missing_information": test_plan.get("missing_information") or [],
        "risks": test_plan.get("risks") or [],
    }


def build_api_section(api_results: dict[str, Any]) -> dict[str, Any]:
    """Build the API Testing report section."""

    if not api_results:
        return ReportSection(
            title="API Testing",
            status="missing",
            notes=["api_result.json was not available for this report."],
        ).model_dump(mode="json")

    summary = api_results.get("summary") or {}
    tests = api_results.get("tests") or []
    has_issues = any(
        int(summary.get(key) or 0) > 0 for key in ("failed", "skipped", "errors")
    )
    status = "partial" if has_issues else "success"
    if not tests:
        status = "partial"
    return ReportSection(
        title="API Testing",
        status=status,
        summary=summary,
        items=[_compact_api_test(test) for test in tests if isinstance(test, dict)],
        notes=["Only planned API tests are included."],
    ).model_dump(mode="json")


def build_ui_section(ui_results: dict[str, Any]) -> dict[str, Any]:
    """Build the UI Testing report section."""

    if not ui_results:
        return ReportSection(
            title="UI Testing",
            status="skipped",
            notes=["No UI results were available for this report."],
        ).model_dump(mode="json")

    summary = ui_results.get("summary") or {}
    tests = ui_results.get("tests") or []
    has_issues = any(
        int(summary.get(key) or 0) > 0 for key in ("failed", "skipped", "errors")
    )
    status = "partial" if has_issues else "success"
    if not tests:
        status = "partial"
    return ReportSection(
        title="UI Testing",
        status=status,
        summary=summary,
        items=[_compact_ui_test(test) for test in tests if isinstance(test, dict)],
        notes=["Only planned UI tests are included."],
    ).model_dump(mode="json")


def build_screenshot_section(screenshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a compact screenshot path section."""

    if not screenshots:
        return ReportSection(
            title="UI Screenshots",
            status="success",
            notes=["No screenshot paths were recorded."],
        ).model_dump(mode="json")
    return ReportSection(
        title="UI Screenshots",
        status="success",
        summary={"count": len(screenshots)},
        items=[item for item in screenshots if isinstance(item, dict)],
        notes=["Screenshot paths are listed without embedding binary content in State."],
    ).model_dump(mode="json")


def build_performance_section(performance_results: dict[str, Any]) -> dict[str, Any]:
    """Build the Performance Testing report section."""

    if not performance_results:
        return ReportSection(
            title="Performance Testing",
            status="skipped",
            notes=["No performance results were available for this report."],
        ).model_dump(mode="json")

    summary = performance_results.get("summary") or {}
    tests = performance_results.get("tests") or []
    has_issues = any(
        int(summary.get(key) or 0) > 0 for key in ("failed", "skipped", "errors")
    )
    status = "partial" if has_issues else "success"
    if not tests:
        status = "partial"
    return ReportSection(
        title="Performance Testing",
        status=status,
        summary=summary,
        items=[
            _compact_performance_test(test)
            for test in tests
            if isinstance(test, dict)
        ],
        notes=["Only safe GET/HEAD performance checks are included."],
    ).model_dump(mode="json")


def build_bug_section(bug_results: dict[str, Any]) -> dict[str, Any]:
    """Build the Bug Analysis report section."""

    if not bug_results:
        return ReportSection(
            title="Bug Analysis",
            status="missing",
            notes=["bug_result.json was not available for this report."],
        ).model_dump(mode="json")

    return ReportSection(
        title="Bug Analysis",
        status="success",
        summary=bug_results.get("summary") or {},
        items=bug_results.get("anomalies") or [],
        notes=["Bug Analysis uses deterministic rules only."],
    ).model_dump(mode="json")


def build_project_section(project_info: dict[str, Any]) -> dict[str, Any]:
    """Build the project metadata report section."""

    if not project_info:
        return ReportSection(
            title="Project",
            status="missing",
            notes=["project_info.json was not available for this report."],
        ).model_dump(mode="json")

    summary = {
        "language": project_info.get("language"),
        "framework": project_info.get("framework"),
        "has_api": project_info.get("has_api"),
        "has_ui": project_info.get("has_ui"),
        "auth_type": project_info.get("auth_type"),
        "candidate_docs_count": len(project_info.get("candidate_docs") or []),
        "candidate_api_files_count": len(project_info.get("candidate_api_files") or []),
        "candidate_ui_files_count": len(project_info.get("candidate_ui_files") or []),
    }
    return ReportSection(
        title="Project",
        status="success",
        summary=summary,
        items=[],
        notes=[],
    ).model_dump(mode="json")


def build_test_plan_section(test_plan: dict[str, Any]) -> dict[str, Any]:
    """Build the Test Plan report section."""

    if not test_plan:
        return ReportSection(
            title="Test Plan",
            status="missing",
            notes=["test_plan.json was not available for this report."],
        ).model_dump(mode="json")
    return ReportSection(
        title="Test Plan",
        status="success",
        summary=summarize_test_plan(test_plan),
        items=[],
        notes=["The plan is grounded in repository evidence and retrieved context."],
    ).model_dump(mode="json")


def collect_recommendations(bug_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect or synthesize recommendations from Bug Analysis output."""

    if not bug_results:
        return []
    recommendations = bug_results.get("recommendations") or []
    if recommendations:
        return recommendations
    generated = []
    for anomaly in bug_results.get("anomalies") or []:
        generated.append(
            {
                "priority": anomaly.get("severity") or "info",
                "title": anomaly.get("title") or "Review anomaly",
                "action": anomaly.get("recommendation") or "Review the anomaly evidence.",
                "related_anomaly_ids": [anomaly.get("id")] if anomaly.get("id") else [],
            }
        )
    return generated


def _report_status(sections: list[dict[str, Any]]) -> str:
    if any(section.get("status") == "error" for section in sections):
        return "error"
    if any(section.get("status") in {"missing", "partial"} for section in sections):
        return "partial"
    return "success"


def build_final_results(context: dict[str, Any]) -> dict[str, Any]:
    """Aggregate context into FinalResults-compatible report data."""

    context = mask_sensitive_report_data(context or {})
    run_id = context.get("run_id") or generate_run_id()
    project_info = context.get("project_info") or {}
    test_plan = context.get("test_plan") or {}
    api_results = context.get("api_results") or {}
    ui_results = context.get("ui_results") or {}
    performance_results = context.get("performance_results") or {}
    performance_artifacts = (
        context.get("performance_artifacts")
        or performance_results.get("artifacts")
        or []
    )
    screenshots = context.get("screenshots") or ui_results.get("screenshots") or []
    bug_results = context.get("bug_results") or {}
    recommendations = context.get("recommendations") or collect_recommendations(bug_results)
    kpis = compute_report_kpis(
        api_results=api_results,
        ui_results=ui_results,
        performance_results=performance_results,
        bug_results=bug_results,
        recommendations=recommendations,
        screenshots=screenshots,
    )
    sections = [
        build_project_section(project_info),
        build_test_plan_section(test_plan),
        build_api_section(api_results),
        build_ui_section(ui_results),
        build_performance_section(performance_results),
        build_bug_section(bug_results),
    ]
    artifact_paths = context.get("artifact_paths") or {}
    final_results = FinalResults(
        run_id=run_id,
        generated_at=current_timestamp(),
        project_info=project_info,
        target_url=context.get("target_url"),
        user_preferences=context.get("user_preferences") or {},
        kpis=ReportKPIs(**kpis),
        test_plan_summary=summarize_test_plan(test_plan),
        api_summary=api_results.get("summary") or {},
        ui_summary=ui_results.get("summary") or {},
        performance_summary=performance_results.get("summary") or {},
        performance_artifacts=performance_artifacts,
        bug_summary=bug_results.get("summary") or {},
        screenshots=screenshots,
        recommendations=recommendations,
        anomalies=bug_results.get("anomalies") or [],
        sections=[ReportSection(**section) for section in sections],
        artifact_paths=ReportArtifactPaths(**artifact_paths),
        limitations=[
            "UI tests use simple Selenium page, form, and text checks.",
            "Performance tests use small safe Locust loads.",
            "External performance targets are skipped by default.",
            "Bug analysis is rule-based.",
            "Dashboard displays generated reports but does not edit results.",
        ],
    )
    data = final_results.model_dump(mode="json")
    data["status"] = _report_status(sections)
    return mask_sensitive_report_data(data)


def build_dashboard_payload(final_results: dict[str, Any]) -> dict[str, Any]:
    """Build compact data for a future dashboard UI."""

    kpis = final_results.get("kpis") or {}
    return {
        "run_id": final_results.get("run_id"),
        "global_score": kpis.get("global_score", 0.0),
        "api": {
            "total_api_tests": kpis.get("total_api_tests", 0),
            "passed": kpis.get("passed", 0),
            "failed": kpis.get("failed", 0),
            "skipped": kpis.get("skipped", 0),
            "errors": kpis.get("errors", 0),
            "pass_rate": kpis.get("pass_rate", 0.0),
        },
        "ui": {
            "total_ui_tests": kpis.get("total_ui_tests", 0),
            "passed": kpis.get("ui_passed", 0),
            "failed": kpis.get("ui_failed", 0),
            "skipped": kpis.get("ui_skipped", 0),
            "errors": kpis.get("ui_errors", 0),
            "pass_rate": kpis.get("ui_pass_rate", 0.0),
            "screenshot_count": kpis.get("screenshot_count", 0),
        },
        "performance": {
            "total_performance_tests": kpis.get("total_performance_tests", 0),
            "passed": kpis.get("performance_passed", 0),
            "failed": kpis.get("performance_failed", 0),
            "skipped": kpis.get("performance_skipped", 0),
            "errors": kpis.get("performance_errors", 0),
            "average_response_time_ms": kpis.get("average_response_time_ms"),
            "p95_response_time_ms": kpis.get("p95_response_time_ms"),
            "overall_failure_rate": kpis.get("overall_failure_rate", 0.0),
        },
        "bugs": {
            "total_anomalies": kpis.get("total_anomalies", 0),
            "high": kpis.get("high_anomalies", 0),
            "medium": kpis.get("medium_anomalies", 0),
            "low": kpis.get("low_anomalies", 0),
            "info": kpis.get("info_anomalies", 0),
        },
        "recommendation_count": kpis.get("recommendation_count", 0),
        "screenshot_count": kpis.get("screenshot_count", 0),
        "report_html_path": (final_results.get("artifact_paths") or {}).get("report_html_path"),
        "status": final_results.get("status", "partial"),
    }
