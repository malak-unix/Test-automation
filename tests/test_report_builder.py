from __future__ import annotations

import json

from test_auto.reporting.html_renderer import render_report_html
from test_auto.reporting.report_builder import (
    build_api_section,
    build_bug_section,
    build_dashboard_payload,
    build_final_results,
    build_project_section,
    summarize_test_plan,
)
from test_auto.shared.schemas import FinalResults


def fake_project_info() -> dict:
    return {
        "language": "Python",
        "framework": "Django REST Framework",
        "has_api": True,
        "has_ui": True,
        "auth_type": "JWT",
        "candidate_docs": ["README.md"],
        "candidate_api_files": ["todo/urls.py"],
        "candidate_ui_files": ["templates/login.html"],
    }


def fake_test_plan() -> dict:
    return {
        "scope": "JWT Todo API",
        "api_tests": [{"id": "API_001"}],
        "ui_tests": [{"id": "UI_001"}],
        "performance_tests": [{"id": "PERF_001"}],
        "missing_information": ["No concrete todo id."],
        "risks": ["Dynamic endpoints are skipped."],
    }


def fake_api_results() -> dict:
    return {
        "summary": {"total_tests": 2, "passed": 1, "failed": 1, "skipped": 0, "errors": 0, "pass_rate": 50.0},
        "tests": [
            {
                "id": "API_001",
                "name": "list_todos",
                "method": "GET",
                "endpoint": "/api/todos/",
                "status": "passed",
                "expected_status": 200,
                "actual_status": 200,
                "duration_ms": 10.0,
                "details": "ok",
            }
        ],
    }


def fake_bug_results() -> dict:
    return {
        "summary": {"total_anomalies": 1, "high": 1, "medium": 0, "low": 0, "info": 0},
        "anomalies": [
            {
                "id": "BUG_001",
                "severity": "high",
                "classification": "security_risk",
                "title": "Authorization bypass",
                "source_agent": "api_testing",
                "recommendation": "Verify authentication and permission checks.",
            }
        ],
        "recommendations": [
            {
                "priority": "high",
                "title": "Review authorization",
                "action": "Verify authentication and permission checks.",
                "related_anomaly_ids": ["BUG_001"],
            }
        ],
    }


def fake_context() -> dict:
    return {
        "run_id": "report_builder_test",
        "target_url": "http://localhost:8000",
        "project_info": fake_project_info(),
        "test_plan": fake_test_plan(),
        "api_results": fake_api_results(),
        "bug_results": fake_bug_results(),
        "user_preferences": {"test_types": ["api"]},
    }


def test_summarize_test_plan() -> None:
    summary = summarize_test_plan(fake_test_plan())

    assert summary["api_tests"] == 1
    assert summary["ui_tests"] == 1
    assert summary["performance_tests"] == 1


def test_build_api_section_with_results() -> None:
    section = build_api_section(fake_api_results())

    assert section["title"] == "API Testing"
    assert section["status"] == "partial"
    assert section["items"]


def test_build_api_section_missing() -> None:
    section = build_api_section({})

    assert section["status"] == "missing"


def test_build_bug_section_with_anomalies() -> None:
    section = build_bug_section(fake_bug_results())

    assert section["items"][0]["classification"] == "security_risk"


def test_build_project_section() -> None:
    section = build_project_section(fake_project_info())

    assert section["summary"]["framework"] == "Django REST Framework"
    assert section["summary"]["language"] == "Python"


def test_build_final_results_validates_schema() -> None:
    final_results = build_final_results(fake_context())

    validated = FinalResults(**final_results)
    assert validated.run_id == "report_builder_test"
    assert final_results["kpis"]["total_api_tests"] == 2


def test_build_dashboard_payload() -> None:
    final_results = build_final_results(fake_context())
    final_results["artifact_paths"]["report_html_path"] = "reports/generated/report_report_builder_test.html"

    payload = build_dashboard_payload(final_results)

    assert payload["run_id"] == "report_builder_test"
    assert payload["global_score"] >= 0
    assert payload["report_html_path"].endswith(".html")


def test_sensitive_values_are_masked() -> None:
    context = fake_context()
    context["api_results"]["tests"][0]["details"] = "Bearer SECRET_TOKEN_SHOULD_NOT_APPEAR"
    context["user_preferences"]["auth_token"] = "SECRET_TOKEN_SHOULD_NOT_APPEAR"

    final_results = build_final_results(context)
    html = render_report_html(final_results)

    assert "SECRET_TOKEN_SHOULD_NOT_APPEAR" not in json.dumps(final_results)
    assert "SECRET_TOKEN_SHOULD_NOT_APPEAR" not in html
