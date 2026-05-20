from __future__ import annotations

from test_auto.reporting.kpi_calculator import (
    compute_api_kpis,
    compute_bug_kpis,
    compute_global_score,
)


def test_compute_api_kpis_from_summary() -> None:
    kpis = compute_api_kpis(
        {"summary": {"total_tests": 4, "passed": 2, "failed": 1, "skipped": 1, "errors": 0, "pass_rate": 50.0}}
    )

    assert kpis["total_api_tests"] == 4
    assert kpis["passed"] == 2
    assert kpis["pass_rate"] == 50.0


def test_compute_api_kpis_from_tests_fallback() -> None:
    kpis = compute_api_kpis(
        {
            "tests": [
                {"status": "passed"},
                {"status": "failed"},
                {"status": "skipped"},
                {"status": "environment_error"},
            ]
        }
    )

    assert kpis["total_api_tests"] == 4
    assert kpis["passed"] == 1
    assert kpis["failed"] == 1
    assert kpis["skipped"] == 1
    assert kpis["errors"] == 1
    assert kpis["pass_rate"] == 25.0


def test_compute_bug_kpis_from_summary() -> None:
    kpis = compute_bug_kpis(
        {"summary": {"total_anomalies": 3, "high": 1, "medium": 1, "low": 0, "info": 1}}
    )

    assert kpis["total_anomalies"] == 3
    assert kpis["high_anomalies"] == 1
    assert kpis["info_anomalies"] == 1


def test_compute_bug_kpis_from_anomalies_fallback() -> None:
    kpis = compute_bug_kpis(
        {"anomalies": [{"severity": "high"}, {"severity": "medium"}, {"severity": "low"}, {"severity": "info"}]}
    )

    assert kpis["total_anomalies"] == 4
    assert kpis["high_anomalies"] == 1
    assert kpis["medium_anomalies"] == 1
    assert kpis["low_anomalies"] == 1
    assert kpis["info_anomalies"] == 1


def test_compute_global_score_bounds() -> None:
    score = compute_global_score(
        {"total_api_tests": 3, "failed": 20, "errors": 20},
        {"high_anomalies": 20, "medium_anomalies": 20, "low_anomalies": 20},
    )

    assert 0 <= score <= 100


def test_compute_global_score_no_tests_is_zero() -> None:
    assert compute_global_score({"total_api_tests": 0}, {}) == 0.0
