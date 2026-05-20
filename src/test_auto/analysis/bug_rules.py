"""Rule application for Bug Analysis Agent outputs."""

from __future__ import annotations

from collections import Counter
from typing import Any

from test_auto.analysis.classifiers import classify_api_test_result, classify_pass_rate
from test_auto.analysis.recommendation_builder import (
    build_global_recommendations,
    build_recommendation_for_classification,
)


def extract_api_tests_from_output(api_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Return API execution test results from an API agent output."""

    tests = (api_results or {}).get("tests") or []
    return list(tests) if isinstance(tests, list) else []


def extract_ui_tests_from_output(ui_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Return UI execution test results from a UI agent output."""

    tests = (ui_results or {}).get("tests") or []
    return list(tests) if isinstance(tests, list) else []


def extract_performance_tests_from_output(perf_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Return performance execution test results from a Performance agent output."""

    tests = (perf_results or {}).get("tests") or []
    return list(tests) if isinstance(tests, list) else []


def _api_evidence(test_result: dict[str, Any], evidence_path: str | None = None) -> dict[str, Any]:
    return {
        "source_agent": "api_testing",
        "test_id": test_result.get("id"),
        "test_name": test_result.get("name"),
        "method": test_result.get("method"),
        "endpoint": test_result.get("endpoint"),
        "expected_status": test_result.get("expected_status"),
        "actual_status": test_result.get("actual_status"),
        "status": test_result.get("status"),
        "details": test_result.get("details"),
        "duration_ms": test_result.get("duration_ms"),
        "evidence_path": evidence_path,
    }


def _summary_evidence(summary: dict[str, Any], evidence_path: str | None = None) -> dict[str, Any]:
    return {
        "source_agent": "api_testing",
        "status": "summary",
        "details": (
            f"total_tests={summary.get('total_tests', 0)}, "
            f"pass_rate={summary.get('pass_rate', 0.0)}"
        ),
        "evidence_path": evidence_path,
    }


def _ui_screenshot_path(test_result: dict[str, Any]) -> str | None:
    screenshot = test_result.get("screenshot")
    if isinstance(screenshot, dict):
        path = screenshot.get("path")
        return str(path) if path else None
    return None


def _ui_evidence(test_result: dict[str, Any], evidence_path: str | None = None) -> dict[str, Any]:
    return {
        "source_agent": "ui_testing",
        "test_id": test_result.get("id"),
        "test_name": test_result.get("name"),
        "flow": test_result.get("flow"),
        "target_path": test_result.get("target_path"),
        "target_url": test_result.get("target_url"),
        "status": test_result.get("status"),
        "details": test_result.get("details"),
        "duration_ms": test_result.get("duration_ms"),
        "screenshot_path": _ui_screenshot_path(test_result),
        "evidence_path": evidence_path,
    }


def _performance_evidence(
    test_result: dict[str, Any],
    evidence_path: str | None = None,
) -> dict[str, Any]:
    return {
        "source_agent": "performance_testing",
        "test_id": test_result.get("id"),
        "test_name": test_result.get("name"),
        "method": test_result.get("method"),
        "endpoint": test_result.get("endpoint"),
        "status": test_result.get("status"),
        "details": test_result.get("details"),
        "evidence_path": evidence_path,
        "users": test_result.get("users"),
        "duration_seconds": test_result.get("duration_seconds"),
        "total_requests": test_result.get("total_requests"),
        "failures": test_result.get("failures"),
        "failure_rate": test_result.get("failure_rate"),
        "average_response_time_ms": test_result.get("average_response_time_ms"),
        "p95_response_time_ms": test_result.get("p95_response_time_ms"),
    }


def _classify_ui_test_result(test_result: dict[str, Any]) -> dict[str, Any]:
    status = str(test_result.get("status") or "").strip().lower()
    error_type = str(test_result.get("error_type") or "").strip().lower()
    effective = error_type or status
    name = str(test_result.get("name") or test_result.get("id") or "UI test")

    if status == "passed":
        return {
            "should_create_anomaly": False,
            "classification": "none",
            "severity": "info",
            "type": "passed",
            "title": f"{name} passed",
            "confidence": 1.0,
        }
    if status == "skipped" or effective == "skipped":
        return {
            "should_create_anomaly": True,
            "classification": "skipped_or_not_executable",
            "severity": "info",
            "type": "skipped_ui_test",
            "title": f"UI test skipped: {name}",
            "confidence": 0.8,
        }
    if effective == "environment_error":
        return {
            "should_create_anomaly": True,
            "classification": "environment_error",
            "severity": "medium",
            "type": "ui_environment_error",
            "title": f"UI environment error: {name}",
            "confidence": 0.85,
        }
    if effective == "timeout_error":
        return {
            "should_create_anomaly": True,
            "classification": "environment_error",
            "severity": "medium",
            "type": "ui_timeout",
            "title": f"UI timeout during: {name}",
            "confidence": 0.75,
        }
    if effective == "selector_error":
        return {
            "should_create_anomaly": True,
            "classification": "test_script_error",
            "severity": "medium",
            "type": "ui_selector_error",
            "title": f"UI selector issue: {name}",
            "confidence": 0.75,
        }
    if effective == "test_data_error":
        return {
            "should_create_anomaly": True,
            "classification": "test_data_error",
            "severity": "low",
            "type": "ui_test_data_error",
            "title": f"UI test data issue: {name}",
            "confidence": 0.7,
        }
    if effective == "assertion_error" or status == "failed":
        return {
            "should_create_anomaly": True,
            "classification": "assertion_error",
            "severity": "medium",
            "type": "ui_assertion_failed",
            "title": f"UI assertion failed: {name}",
            "confidence": 0.75,
        }
    return {
        "should_create_anomaly": True,
        "classification": "unknown",
        "severity": "low",
        "type": "unclassified_ui_anomaly",
        "title": f"Unclassified UI anomaly: {name}",
        "confidence": 0.5,
    }


def _metric_threshold_failed(test_result: dict[str, Any], metric_name: str) -> bool:
    for threshold in test_result.get("threshold_results") or []:
        if not isinstance(threshold, dict):
            continue
        if threshold.get("name") == metric_name and threshold.get("passed") is False:
            return True
    return False


def _classify_performance_test_result(test_result: dict[str, Any]) -> dict[str, Any]:
    status = str(test_result.get("status") or "").strip().lower()
    error_type = str(test_result.get("error_type") or "").strip().lower()
    effective = error_type or status
    name = str(test_result.get("name") or test_result.get("id") or "Performance test")
    failure_rate = float(test_result.get("failure_rate") or 0.0)

    if status == "passed":
        return {
            "should_create_anomaly": False,
            "classification": "none",
            "severity": "info",
            "type": "passed",
            "title": f"{name} passed",
            "confidence": 1.0,
        }
    if status == "skipped" or effective == "skipped":
        return {
            "should_create_anomaly": True,
            "classification": "skipped_or_not_executable",
            "severity": "info",
            "type": "skipped_performance_test",
            "title": f"Performance test skipped: {name}",
            "confidence": 0.8,
        }
    if effective == "environment_error":
        return {
            "should_create_anomaly": True,
            "classification": "environment_error",
            "severity": "medium",
            "type": "performance_environment_error",
            "title": f"Performance environment error: {name}",
            "confidence": 0.85,
        }
    if effective == "configuration_error" or status == "configuration_error":
        return {
            "should_create_anomaly": True,
            "classification": "test_script_error",
            "severity": "medium",
            "type": "performance_configuration_error",
            "title": f"Performance configuration issue: {name}",
            "confidence": 0.8,
        }
    if status == "performance_threshold_failed" or effective == "performance_threshold_failed":
        severity = "high" if failure_rate > 20 else "medium"
        if _metric_threshold_failed(test_result, "failure_rate"):
            anomaly_type = "high_performance_failure_rate"
        elif _metric_threshold_failed(test_result, "p95_response_time"):
            anomaly_type = "slow_p95_response_time"
        elif _metric_threshold_failed(test_result, "average_response_time"):
            anomaly_type = "slow_average_response_time"
        else:
            anomaly_type = "performance_threshold_failed"
        return {
            "should_create_anomaly": True,
            "classification": "performance_anomaly",
            "severity": severity,
            "type": anomaly_type,
            "title": f"Performance threshold failed: {name}",
            "confidence": 0.8,
        }
    if status in {"failed", "error"}:
        return {
            "should_create_anomaly": True,
            "classification": "performance_anomaly",
            "severity": "medium",
            "type": "performance_test_failed",
            "title": f"Performance test failed: {name}",
            "confidence": 0.7,
        }
    return {
        "should_create_anomaly": True,
        "classification": "unknown",
        "severity": "low",
        "type": "unclassified_performance_anomaly",
        "title": f"Unclassified performance anomaly: {name}",
        "confidence": 0.5,
    }


def analyze_api_results(
    api_results: dict[str, Any],
    thresholds: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Analyze API result tests and aggregate pass rate."""

    anomalies: list[dict[str, Any]] = []
    tests = extract_api_tests_from_output(api_results)
    evidence_path = (api_results.get("metadata") or {}).get("api_result_path")

    for index, test_result in enumerate(tests, start=1):
        enriched_result = {**test_result, "thresholds": thresholds or {}}
        classification = classify_api_test_result(enriched_result)
        if not classification.get("should_create_anomaly"):
            continue
        evidence = _api_evidence(test_result, evidence_path=evidence_path)
        recommendation = build_recommendation_for_classification(
            classification["classification"],
            classification["type"],
            evidence,
        )
        anomalies.append(
            {
                "id": f"BUG_API_{index:03d}",
                "type": classification["type"],
                "severity": classification["severity"],
                "source_agent": "api_testing",
                "classification": classification["classification"],
                "title": classification["title"],
                "evidence": evidence,
                "recommendation": recommendation,
                "confidence": classification["confidence"],
            }
        )

    summary = api_results.get("summary") or {}
    for index, pass_rate_anomaly in enumerate(
        classify_pass_rate(summary, thresholds),
        start=1,
    ):
        evidence = _summary_evidence(summary, evidence_path=evidence_path)
        recommendation = build_recommendation_for_classification(
            pass_rate_anomaly["classification"],
            pass_rate_anomaly["type"],
            evidence,
        )
        anomalies.append(
            {
                "id": f"BUG_API_SUMMARY_{index:03d}",
                "type": pass_rate_anomaly["type"],
                "severity": pass_rate_anomaly["severity"],
                "source_agent": "api_testing",
                "classification": pass_rate_anomaly["classification"],
                "title": pass_rate_anomaly["title"],
                "evidence": evidence,
                "recommendation": recommendation,
                "confidence": pass_rate_anomaly["confidence"],
            }
        )

    return anomalies


def analyze_ui_results(ui_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze UI execution results and produce UI-specific anomalies."""

    anomalies: list[dict[str, Any]] = []
    tests = extract_ui_tests_from_output(ui_results)
    evidence_path = (ui_results.get("metadata") or {}).get("ui_result_path")

    for index, test_result in enumerate(tests, start=1):
        classification = _classify_ui_test_result(test_result)
        if not classification.get("should_create_anomaly"):
            continue
        evidence = _ui_evidence(test_result, evidence_path=evidence_path)
        recommendation = build_recommendation_for_classification(
            classification["classification"],
            classification["type"],
            evidence,
        )
        anomalies.append(
            {
                "id": f"BUG_UI_{index:03d}",
                "type": classification["type"],
                "severity": classification["severity"],
                "source_agent": "ui_testing",
                "classification": classification["classification"],
                "title": classification["title"],
                "evidence": evidence,
                "recommendation": recommendation,
                "confidence": classification["confidence"],
            }
        )

    summary = ui_results.get("summary") or {}
    if not tests and summary:
        total = int(summary.get("total_tests") or 0)
        if total == 0:
            anomalies.append(
                {
                    "id": "BUG_UI_SUMMARY_001",
                    "type": "no_ui_tests_executed",
                    "severity": "info",
                    "source_agent": "ui_testing",
                    "classification": "skipped_or_not_executable",
                    "title": "No UI tests were executed",
                    "evidence": {
                        "source_agent": "ui_testing",
                        "details": "ui_results contained no executable tests.",
                        "evidence_path": evidence_path,
                    },
                    "recommendation": build_recommendation_for_classification(
                        "skipped_or_not_executable",
                        "no_ui_tests_executed",
                        {},
                    ),
                    "confidence": 0.9,
                }
            )
    return anomalies


def analyze_performance_results(
    perf_results: dict[str, Any],
) -> list[dict[str, Any]]:
    """Analyze Performance execution results and produce performance anomalies."""

    anomalies: list[dict[str, Any]] = []
    tests = extract_performance_tests_from_output(perf_results)
    evidence_path = (perf_results.get("metadata") or {}).get("performance_result_path")

    for index, test_result in enumerate(tests, start=1):
        classification = _classify_performance_test_result(test_result)
        if not classification.get("should_create_anomaly"):
            continue
        evidence = _performance_evidence(test_result, evidence_path=evidence_path)
        recommendation = build_recommendation_for_classification(
            classification["classification"],
            classification["type"],
            evidence,
        )
        anomalies.append(
            {
                "id": f"BUG_PERF_{index:03d}",
                "type": classification["type"],
                "severity": classification["severity"],
                "source_agent": "performance_testing",
                "classification": classification["classification"],
                "title": classification["title"],
                "evidence": evidence,
                "recommendation": recommendation,
                "confidence": classification["confidence"],
            }
        )
    return anomalies


def compute_bug_summary(anomalies: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate bug-analysis counts."""

    severities = Counter(str(item.get("severity") or "info") for item in anomalies)
    classifications = Counter(
        str(item.get("classification") or "unknown")
        for item in anomalies
    )
    return {
        "total_anomalies": len(anomalies),
        "high": severities.get("high", 0),
        "medium": severities.get("medium", 0),
        "low": severities.get("low", 0),
        "info": severities.get("info", 0),
        "by_classification": dict(sorted(classifications.items())),
    }

def analyze_all_results(
    api_results: dict[str, Any] | None = None,
    ui_results: dict[str, Any] | None = None,
    perf_results: dict[str, Any] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze available API, UI, and future result payloads."""

    anomalies: list[dict[str, Any]] = []
    if api_results:
        anomalies.extend(analyze_api_results(api_results, thresholds=thresholds))
    elif not ui_results and not perf_results:
        anomalies.append(
            {
                "id": "BUG_API_001",
                "type": "no_api_results_available",
                "severity": "info",
                "source_agent": "api_testing",
                "classification": "skipped_or_not_executable",
                "title": "No API results were available for bug analysis",
                "evidence": {
                    "source_agent": "api_testing",
                    "details": "api_results or api_result.json was not provided.",
                },
                "recommendation": "Run the API Testing Agent or provide api_result.json before assigning application bugs.",
                "confidence": 0.9,
            }
        )

    if ui_results:
        anomalies.extend(analyze_ui_results(ui_results))

    if perf_results:
        anomalies.extend(analyze_performance_results(perf_results))

    summary = compute_bug_summary(anomalies)
    return {
        "summary": summary,
        "anomalies": anomalies,
        "recommendations": build_global_recommendations(anomalies),
    }
