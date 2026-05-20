"""KPI calculations for final reporting."""

from __future__ import annotations

from typing import Any


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_api_kpis(api_results: dict[str, Any]) -> dict[str, Any]:
    """Compute API execution KPIs from summary or test result fallback."""

    api_results = api_results or {}
    summary = api_results.get("summary") or {}
    if summary:
        total = _to_int(summary.get("total_tests"))
        passed = _to_int(summary.get("passed"))
        failed = _to_int(summary.get("failed"))
        skipped = _to_int(summary.get("skipped"))
        errors = _to_int(summary.get("errors"))
        pass_rate = _to_float(summary.get("pass_rate"))
    else:
        tests = api_results.get("tests") or []
        total = len(tests) if isinstance(tests, list) else 0
        passed = failed = skipped = errors = 0
        for test in tests if isinstance(tests, list) else []:
            status = str(test.get("status") or "").lower()
            if status == "passed":
                passed += 1
            elif status == "skipped":
                skipped += 1
            elif status in {"failed", "assertion_error"}:
                failed += 1
            elif status in {"error", "environment_error", "test_data_error"}:
                errors += 1
        pass_rate = round((passed / total) * 100, 2) if total else 0.0
    return {
        "total_api_tests": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "pass_rate": pass_rate,
    }


def compute_bug_kpis(bug_results: dict[str, Any]) -> dict[str, Any]:
    """Compute anomaly KPIs from bug summary or anomaly fallback."""

    bug_results = bug_results or {}
    summary = bug_results.get("summary") or {}
    if summary:
        return {
            "total_anomalies": _to_int(summary.get("total_anomalies")),
            "high_anomalies": _to_int(summary.get("high")),
            "medium_anomalies": _to_int(summary.get("medium")),
            "low_anomalies": _to_int(summary.get("low")),
            "info_anomalies": _to_int(summary.get("info")),
        }

    counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
    anomalies = bug_results.get("anomalies") or []
    for anomaly in anomalies if isinstance(anomalies, list) else []:
        severity = str(anomaly.get("severity") or "info").lower()
        if severity in counts:
            counts[severity] += 1
    return {
        "total_anomalies": sum(counts.values()),
        "high_anomalies": counts["high"],
        "medium_anomalies": counts["medium"],
        "low_anomalies": counts["low"],
        "info_anomalies": counts["info"],
    }


def compute_ui_kpis(
    ui_results: dict[str, Any],
    screenshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute UI execution KPIs from summary or test result fallback."""

    ui_results = ui_results or {}
    summary = ui_results.get("summary") or {}
    if summary:
        total = _to_int(summary.get("total_tests"))
        passed = _to_int(summary.get("passed"))
        failed = _to_int(summary.get("failed"))
        skipped = _to_int(summary.get("skipped"))
        errors = _to_int(summary.get("errors"))
        pass_rate = _to_float(summary.get("pass_rate"))
    else:
        tests = ui_results.get("tests") or []
        total = len(tests) if isinstance(tests, list) else 0
        passed = failed = skipped = errors = 0
        for test in tests if isinstance(tests, list) else []:
            status = str(test.get("status") or "").lower()
            if status == "passed":
                passed += 1
            elif status == "skipped":
                skipped += 1
            elif status in {"failed", "assertion_error", "selector_error"}:
                failed += 1
            elif status in {"error", "environment_error", "timeout_error", "test_data_error"}:
                errors += 1
        pass_rate = round((passed / total) * 100, 2) if total else 0.0

    screenshot_items = screenshots
    if screenshot_items is None:
        screenshot_items = ui_results.get("screenshots") or []
    return {
        "total_ui_tests": total,
        "ui_passed": passed,
        "ui_failed": failed,
        "ui_skipped": skipped,
        "ui_errors": errors,
        "ui_pass_rate": pass_rate,
        "screenshot_count": len(screenshot_items) if isinstance(screenshot_items, list) else 0,
    }


def compute_performance_kpis(performance_results: dict[str, Any]) -> dict[str, Any]:
    """Compute performance execution KPIs from summary or test fallback."""

    performance_results = performance_results or {}
    summary = performance_results.get("summary") or {}
    if summary:
        return {
            "total_performance_tests": _to_int(summary.get("total_tests")),
            "performance_passed": _to_int(summary.get("passed")),
            "performance_failed": _to_int(summary.get("failed")),
            "performance_skipped": _to_int(summary.get("skipped")),
            "performance_errors": _to_int(summary.get("errors")),
            "average_response_time_ms": (
                None
                if summary.get("average_response_time_ms") is None
                else _to_float(summary.get("average_response_time_ms"))
            ),
            "p95_response_time_ms": (
                None
                if summary.get("p95_response_time_ms") is None
                else _to_float(summary.get("p95_response_time_ms"))
            ),
            "overall_failure_rate": _to_float(summary.get("overall_failure_rate")),
        }

    tests = performance_results.get("tests") or []
    total = len(tests) if isinstance(tests, list) else 0
    passed = failed = skipped = errors = 0
    avg_values = []
    p95_values = []
    failure_rates = []
    for test in tests if isinstance(tests, list) else []:
        status = str(test.get("status") or "").lower()
        if status == "passed":
            passed += 1
        elif status == "skipped":
            skipped += 1
        elif status in {"failed", "performance_threshold_failed"}:
            failed += 1
        elif status in {"error", "environment_error", "configuration_error"}:
            errors += 1
        if test.get("average_response_time_ms") is not None:
            avg_values.append(_to_float(test.get("average_response_time_ms")))
        if test.get("p95_response_time_ms") is not None:
            p95_values.append(_to_float(test.get("p95_response_time_ms")))
        if test.get("failure_rate") is not None:
            failure_rates.append(_to_float(test.get("failure_rate")))
    return {
        "total_performance_tests": total,
        "performance_passed": passed,
        "performance_failed": failed,
        "performance_skipped": skipped,
        "performance_errors": errors,
        "average_response_time_ms": round(sum(avg_values) / len(avg_values), 2)
        if avg_values
        else None,
        "p95_response_time_ms": round(sum(p95_values) / len(p95_values), 2)
        if p95_values
        else None,
        "overall_failure_rate": round(sum(failure_rates) / len(failure_rates), 2)
        if failure_rates
        else 0.0,
    }


def compute_global_score(
    api_kpis: dict[str, Any],
    bug_kpis: dict[str, Any],
    ui_kpis: dict[str, Any] | None = None,
    performance_kpis: dict[str, Any] | None = None,
) -> float:
    """Compute a bounded project health score from API, UI, performance, and bugs."""

    ui_kpis = ui_kpis or {}
    performance_kpis = performance_kpis or {}
    has_api = _to_int(api_kpis.get("total_api_tests")) > 0
    has_ui = _to_int(ui_kpis.get("total_ui_tests")) > 0
    has_performance = _to_int(performance_kpis.get("total_performance_tests")) > 0
    if not has_api and not has_ui and not has_performance:
        return 0.0

    score = 100.0
    score -= _to_int(api_kpis.get("failed")) * 5
    score -= _to_int(api_kpis.get("errors")) * 3
    score -= _to_int(ui_kpis.get("ui_failed")) * 5
    score -= _to_int(ui_kpis.get("ui_errors")) * 3
    score -= _to_int(performance_kpis.get("performance_failed")) * 5
    score -= _to_int(performance_kpis.get("performance_errors")) * 3
    score -= _to_int(bug_kpis.get("high_anomalies")) * 15
    score -= _to_int(bug_kpis.get("medium_anomalies")) * 8
    score -= _to_int(bug_kpis.get("low_anomalies")) * 3
    return round(max(0.0, min(100.0, score)), 2)


def compute_report_kpis(
    api_results: dict[str, Any],
    bug_results: dict[str, Any] | None = None,
    recommendations: list[dict[str, Any]] | None = None,
    ui_results: dict[str, Any] | None = None,
    screenshots: list[dict[str, Any]] | None = None,
    performance_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine all report KPIs into one schema-compatible dict."""

    api_kpis = compute_api_kpis(api_results)
    ui_kpis = compute_ui_kpis(ui_results, screenshots=screenshots)
    performance_kpis = compute_performance_kpis(performance_results or {})
    bug_kpis = compute_bug_kpis(bug_results)
    return {
        **api_kpis,
        **ui_kpis,
        **performance_kpis,
        **bug_kpis,
        "recommendation_count": len(recommendations or []),
        "global_score": compute_global_score(
            api_kpis,
            bug_kpis,
            ui_kpis,
            performance_kpis,
        ),
    }
