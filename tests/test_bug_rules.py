from __future__ import annotations

import json

from test_auto.analysis.bug_rules import compute_bug_summary
from test_auto.analysis.classifiers import classify_api_test_result
from test_auto.analysis.recommendation_builder import build_global_recommendations
from test_auto.tools.bug_tools import mask_sensitive_values


def test_classify_passed_test_no_anomaly() -> None:
    result = classify_api_test_result({"status": "passed", "method": "GET", "endpoint": "/api/todos/"})

    assert result["should_create_anomaly"] is False


def test_classify_environment_error() -> None:
    result = classify_api_test_result(
        {
            "status": "environment_error",
            "method": "GET",
            "endpoint": "/api/todos/",
            "details": "Connection refused",
        }
    )

    assert result["classification"] == "environment_error"
    assert result["severity"] == "medium"


def test_classify_auth_bypass_high_security() -> None:
    result = classify_api_test_result(
        {
            "status": "assertion_error",
            "method": "GET",
            "endpoint": "/api/todos/",
            "expected_status": 401,
            "actual_status": 200,
        }
    )

    assert result["classification"] == "security_risk"
    assert result["severity"] == "high"
    assert result["type"] == "authorization_bypass"


def test_classify_http_500_high_application_bug() -> None:
    result = classify_api_test_result(
        {
            "status": "assertion_error",
            "method": "GET",
            "endpoint": "/api/todos/",
            "expected_status": 200,
            "actual_status": 500,
        }
    )

    assert result["classification"] == "application_bug"
    assert result["severity"] == "high"
    assert result["type"] == "server_error"


def test_classify_unexpected_status_medium() -> None:
    result = classify_api_test_result(
        {
            "status": "assertion_error",
            "method": "POST",
            "endpoint": "/api/todos/",
            "expected_status": 201,
            "actual_status": 400,
        }
    )

    assert result["classification"] in {"application_bug", "assertion_error"}
    assert result["severity"] == "medium"


def test_classify_skipped_dynamic_endpoint_info() -> None:
    result = classify_api_test_result(
        {
            "status": "skipped",
            "method": "GET",
            "endpoint": "/api/todos/<int:pk>/",
            "details": "Endpoint contains unresolved dynamic path parameters.",
        }
    )

    assert result["classification"] == "skipped_or_not_executable"
    assert result["severity"] == "info"
    assert result["should_create_anomaly"] is True


def test_compute_bug_summary() -> None:
    summary = compute_bug_summary(
        [
            {"severity": "high", "classification": "security_risk"},
            {"severity": "medium", "classification": "environment_error"},
            {"severity": "info", "classification": "skipped_or_not_executable"},
        ]
    )

    assert summary["total_anomalies"] == 3
    assert summary["high"] == 1
    assert summary["medium"] == 1
    assert summary["info"] == 1
    assert summary["by_classification"]["security_risk"] == 1


def test_build_global_recommendations() -> None:
    recommendations = build_global_recommendations(
        [
            {
                "id": "BUG_API_001",
                "severity": "high",
                "classification": "security_risk",
                "type": "authorization_bypass",
                "evidence": {},
            }
        ]
    )

    assert recommendations
    assert recommendations[0]["priority"] == "high"
    assert recommendations[0]["related_anomaly_ids"] == ["BUG_API_001"]


def test_mask_sensitive_values() -> None:
    masked = mask_sensitive_values(
        {
            "Authorization": "Bearer SECRET_TOKEN_SHOULD_NOT_APPEAR",
            "token": "SECRET_TOKEN_SHOULD_NOT_APPEAR",
            "Cookie": "sessionid=SECRET_TOKEN_SHOULD_NOT_APPEAR",
        }
    )

    assert "SECRET_TOKEN_SHOULD_NOT_APPEAR" not in json.dumps(masked)
    assert "***MASKED***" in json.dumps(masked)
