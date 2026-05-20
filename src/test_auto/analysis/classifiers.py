"""Deterministic classification rules for bug analysis."""

from __future__ import annotations

from typing import Any


DEFAULT_THRESHOLDS = {
    "pass_rate_high_risk_threshold": 50,
    "pass_rate_medium_risk_threshold": 80,
    "slow_response_ms_threshold": 2000,
    "include_skipped_as_info": True,
}


def _thresholds(thresholds: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(DEFAULT_THRESHOLDS)
    merged.update(thresholds or {})
    return merged


def normalize_status(value: str | None) -> str:
    """Normalize a result status string for rule matching."""

    if not value:
        return "unknown"
    return str(value).strip().lower().replace(" ", "_")


def _important_skip(details: str, thresholds: dict[str, Any]) -> bool:
    if not thresholds.get("include_skipped_as_info", True):
        return False
    lowered = details.lower()
    return any(
        marker in lowered
        for marker in [
            "dynamic",
            "mutating",
            "not executable",
            "unresolved",
            "unknown",
            "cannot be safely executed",
        ]
    )


def classify_api_test_result(test_result: dict[str, Any]) -> dict[str, Any]:
    """Classify one API execution result into a bug/risk category."""

    thresholds = _thresholds(test_result.get("thresholds"))
    status = normalize_status(test_result.get("status"))
    error_type = normalize_status(test_result.get("error_type"))
    details = str(test_result.get("details") or "")
    expected_status = test_result.get("expected_status")
    actual_status = test_result.get("actual_status")
    duration_ms = test_result.get("duration_ms")
    method = str(test_result.get("method") or "UNKNOWN").upper()
    endpoint = str(test_result.get("endpoint") or "")

    if status == "passed":
        return {
            "should_create_anomaly": False,
            "classification": "none",
            "severity": "info",
            "type": "passed",
            "title": "API test passed",
            "confidence": 1.0,
        }

    if expected_status in {401, 403} and actual_status == 200:
        return {
            "should_create_anomaly": True,
            "classification": "security_risk",
            "severity": "high",
            "type": "authorization_bypass",
            "title": f"Possible authorization bypass on {method} {endpoint}",
            "confidence": 0.9,
        }

    if isinstance(actual_status, int) and actual_status >= 500:
        return {
            "should_create_anomaly": True,
            "classification": "application_bug",
            "severity": "high",
            "type": "server_error",
            "title": f"Server error from {method} {endpoint}",
            "confidence": 0.85,
        }

    if status == "skipped":
        return {
            "should_create_anomaly": _important_skip(details, thresholds),
            "classification": "skipped_or_not_executable",
            "severity": "info",
            "type": "skipped_api_test",
            "title": f"API test skipped for {method} {endpoint}",
            "confidence": 0.8,
        }

    if status == "environment_error" or error_type == "environment_error":
        lowered_details = details.lower()
        anomaly_type = "target_unreachable" if any(
            marker in lowered_details
            for marker in ["connection", "refused", "timed out", "timeout", "unreachable"]
        ) else "api_environment_error"
        return {
            "should_create_anomaly": True,
            "classification": "environment_error",
            "severity": "medium",
            "type": anomaly_type,
            "title": f"API environment error for {method} {endpoint}",
            "confidence": 0.85,
        }

    if status == "test_data_error" or error_type == "test_data_error":
        return {
            "should_create_anomaly": True,
            "classification": "test_data_error",
            "severity": "low",
            "type": "invalid_test_data",
            "title": f"API test data issue for {method} {endpoint}",
            "confidence": 0.75,
        }

    if status == "assertion_error" or error_type == "assertion_error":
        if expected_status is not None and actual_status is not None and expected_status != actual_status:
            return {
                "should_create_anomaly": True,
                "classification": "application_bug",
                "severity": "medium",
                "type": "unexpected_status_code",
                "title": f"Unexpected status code from {method} {endpoint}",
                "confidence": 0.75,
            }
        return {
            "should_create_anomaly": True,
            "classification": "assertion_error",
            "severity": "medium",
            "type": "response_assertion_failed",
            "title": f"Response assertion failed for {method} {endpoint}",
            "confidence": 0.7,
        }

    if expected_status is not None and actual_status is not None and expected_status != actual_status:
        return {
            "should_create_anomaly": True,
            "classification": "application_bug",
            "severity": "medium",
            "type": "unexpected_status_code",
            "title": f"Unexpected status code from {method} {endpoint}",
            "confidence": 0.7,
        }

    if isinstance(duration_ms, (int, float)) and duration_ms > thresholds["slow_response_ms_threshold"]:
        return {
            "should_create_anomaly": True,
            "classification": "unknown",
            "severity": "medium",
            "type": "slow_api_response",
            "title": f"Slow API response from {method} {endpoint}",
            "confidence": 0.65,
        }

    return {
        "should_create_anomaly": True,
        "classification": "unknown",
        "severity": "low",
        "type": "unclassified_api_anomaly",
        "title": f"Unclassified API anomaly for {method} {endpoint}",
        "confidence": 0.5,
    }


def classify_pass_rate(
    summary: dict[str, Any],
    thresholds: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Classify the aggregate API pass rate into summary anomalies."""

    limits = _thresholds(thresholds)
    total_tests = int(summary.get("total_tests") or 0)
    pass_rate = float(summary.get("pass_rate") or 0.0)
    if total_tests == 0:
        return [
            {
                "classification": "skipped_or_not_executable",
                "severity": "info",
                "type": "no_api_tests_executed",
                "title": "No API tests were executed",
                "confidence": 0.9,
            }
        ]
    if pass_rate < float(limits["pass_rate_high_risk_threshold"]):
        return [
            {
                "classification": "application_bug",
                "severity": "high",
                "type": "low_api_pass_rate",
                "title": f"API pass rate is critically low ({pass_rate}%)",
                "confidence": 0.8,
            }
        ]
    if pass_rate < float(limits["pass_rate_medium_risk_threshold"]):
        return [
            {
                "classification": "application_bug",
                "severity": "medium",
                "type": "low_api_pass_rate",
                "title": f"API pass rate is below expected threshold ({pass_rate}%)",
                "confidence": 0.75,
            }
        ]
    return []
