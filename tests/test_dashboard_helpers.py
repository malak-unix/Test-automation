from __future__ import annotations

import json
from pathlib import Path

from test_auto.interface.dashboard_helpers import (
    list_recent_runs,
    load_run_summary,
    mask_sensitive_for_display,
)
from test_auto.interface.run_service import (
    build_initial_state_from_form,
    load_report_html_for_display,
    summarize_final_state,
)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_build_initial_state_from_form_defaults() -> None:
    state = build_initial_state_from_form({"target_url": "http://localhost:8000"})

    assert state["target_url"] == "http://localhost:8000"
    assert state["user_preferences"]["test_types"] == ["api", "ui", "performance"]
    assert state["user_preferences"]["planner_use_llm"] is True
    assert state["user_preferences"]["allow_mutating_api_tests"] is False


def test_build_initial_state_from_form_checkboxes() -> None:
    state = build_initial_state_from_form(
        {
            "target_url": "http://localhost:8000",
            "allow_mutating_api_tests": "on",
            "skip_bug_analysis": "true",
            "skip_report": "1",
        }
    )

    assert state["user_preferences"]["allow_mutating_api_tests"] is True
    assert state["user_preferences"]["skip_bug_analysis"] is True
    assert state["user_preferences"]["skip_report"] is True


def test_summarize_final_state() -> None:
    summary = summarize_final_state(
        {
            "run_id": "summary_run",
            "selected_agents": ["repository_analyzer", "report"],
            "target_url": "http://localhost:8000",
            "project_info": {"framework": "Django REST Framework"},
            "api_results": {"summary": {"total_tests": 2, "passed": 1, "pass_rate": 50.0}},
            "bug_results": {"summary": {"total_anomalies": 1, "high": 1}},
            "final_results": {"kpis": {"global_score": 80, "recommendation_count": 2}},
            "errors": [],
        }
    )

    assert summary["run_id"] == "summary_run"
    assert summary["framework"] == "Django REST Framework"
    assert summary["api_summary"]["total_tests"] == 2
    assert summary["bug_summary"]["total_anomalies"] == 1
    assert summary["global_score"] == 80


def test_list_recent_runs_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert list_recent_runs() == []


def test_load_run_summary_fake_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_id = "fake_dashboard_run"
    write_json(
        Path("results") / "runs" / run_id / "final_results.json",
        {
            "status": "success",
            "target_url": "http://localhost:8000",
            "project_info": {"framework": "Django REST Framework"},
            "api_summary": {"total_tests": 1, "pass_rate": 100.0},
            "bug_summary": {"total_anomalies": 0},
            "kpis": {"global_score": 100.0, "pass_rate": 100.0, "total_anomalies": 0},
            "artifact_paths": {"report_html_path": f"reports/generated/report_{run_id}.html"},
        },
    )

    summary = load_run_summary(run_id)

    assert summary["run_id"] == run_id
    assert summary["framework"] == "Django REST Framework"
    assert summary["global_score"] == 100.0


def test_mask_sensitive_for_display() -> None:
    masked = mask_sensitive_for_display({"details": "Bearer SECRET_TOKEN_SHOULD_NOT_APPEAR"})

    assert "SECRET_TOKEN_SHOULD_NOT_APPEAR" not in json.dumps(masked)


def test_load_report_html_for_display_safe_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = Path("reports") / "generated" / "report_test.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<h1>Report</h1>", encoding="utf-8")

    assert "Report" in load_report_html_for_display(str(path))


def test_load_report_html_for_display_rejects_unsafe_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    unsafe = tmp_path / "secret.html"
    unsafe.write_text("secret", encoding="utf-8")

    assert load_report_html_for_display(str(unsafe)) == ""
