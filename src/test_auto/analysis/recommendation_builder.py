"""Recommendation builders for classified bug-analysis anomalies."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_recommendation_for_classification(
    classification: str,
    anomaly_type: str,
    evidence: dict[str, Any],
) -> str:
    """Return a concise action recommendation for one classification."""

    source_agent = str((evidence or {}).get("source_agent") or "")
    if source_agent == "ui_testing" and classification == "environment_error":
        return "Verify that the target web application and browser are available before interpreting UI failures."
    if source_agent == "ui_testing" and classification == "test_script_error":
        return "Review UI locator strategy or prefer stable data-testid/accessibility labels."
    if source_agent == "ui_testing" and classification == "assertion_error":
        return "Verify expected UI text/form behavior against the application requirements."
    if source_agent == "ui_testing" and classification == "skipped_or_not_executable":
        return "Review planned UI flow and provide missing preconditions."
    if source_agent == "performance_testing" and classification == "performance_anomaly":
        if anomaly_type == "high_performance_failure_rate":
            return "Reduce request failures or increase capacity before higher load."
        return "Check slow endpoints, database queries, and N+1 query patterns."
    if source_agent == "performance_testing" and classification == "environment_error":
        return "Verify that the target app is running before interpreting performance failures."
    if source_agent == "performance_testing" and classification == "test_script_error":
        return "Verify Locust installation and generated performance test configuration."
    if source_agent == "performance_testing" and classification == "skipped_or_not_executable":
        return "Review performance target safety settings and provide a safe GET or HEAD endpoint."
    if classification == "environment_error":
        return "Verify that the target application is running and reachable at target_url before interpreting API failures."
    if classification == "security_risk" and anomaly_type == "authorization_bypass":
        return "Verify authentication and permission checks for this endpoint."
    if classification == "application_bug" and anomaly_type == "server_error":
        return "Inspect server logs and handler code for the endpoint returning HTTP 5xx."
    if classification == "application_bug" and anomaly_type == "unexpected_status_code":
        return "Compare the endpoint implementation with the planned expected behavior and API documentation."
    if classification == "test_data_error":
        return "Review the generated test data or required preconditions for this API test."
    if classification == "skipped_or_not_executable":
        return "Resolve dynamic path parameters or provide test data before executing this endpoint."
    if classification == "assertion_error":
        return "Review the response body and assertion definition for this planned test."
    if anomaly_type == "slow_api_response":
        return "Measure the endpoint again under a controlled environment and inspect slow handler or database paths."
    return "Review the captured evidence and refine the test plan or implementation before assigning root cause."


def build_global_recommendations(anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group anomalies into compact recommendation objects."""

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for anomaly in anomalies:
        grouped[
            (
                str(anomaly.get("severity") or "info"),
                str(anomaly.get("classification") or "unknown"),
            )
        ].append(anomaly)

    priority_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    recommendations = []
    for (severity, classification), items in sorted(
        grouped.items(),
        key=lambda item: (priority_order.get(item[0][0], 99), item[0][1]),
    ):
        first = items[0]
        recommendations.append(
            {
                "priority": severity,
                "title": f"Address {classification.replace('_', ' ')} findings",
                "action": build_recommendation_for_classification(
                    classification,
                    str(first.get("type") or "unknown"),
                    first.get("evidence") if isinstance(first.get("evidence"), dict) else {},
                ),
                "related_anomaly_ids": [str(item.get("id")) for item in items],
            }
        )
    return recommendations
