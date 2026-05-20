from __future__ import annotations

import json
from pathlib import Path

from test_auto.agents.report_agent import report_node, run_report_agent_alone
from test_auto.tools.report_tools import load_report_context_from_run_dir


def fake_context() -> dict:
    return {
        "run_id": "report_agent_test",
        "target_url": "http://localhost:8000",
        "project_info": {
            "language": "Python",
            "framework": "Django REST Framework",
            "has_api": True,
            "has_ui": True,
            "auth_type": "JWT",
            "candidate_docs": ["README.md"],
            "candidate_api_files": ["todo/urls.py"],
            "candidate_ui_files": ["templates/login.html"],
        },
        "test_plan": {
            "scope": "JWT Todo API",
            "api_tests": [{"id": "API_001", "endpoint": "/api/todos/"}],
            "ui_tests": [],
            "performance_tests": [],
            "missing_information": [],
            "risks": [],
        },
        "api_results": {
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
                    "duration_ms": 9.0,
                    "details": "ok",
                }
            ],
        },
        "bug_results": {
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
        },
        "recommendations": [
            {
                "priority": "high",
                "title": "Review authorization",
                "action": "Verify authentication and permission checks.",
                "related_anomaly_ids": ["BUG_001"],
            }
        ],
        "errors": [],
        "agent_logs": [],
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_run_report_agent_alone_fake_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_report_agent_alone(context=fake_context())

    assert result["run_id"] == "report_agent_test"
    assert result["final_results"]
    assert Path(result["final_results_path"]).exists()
    assert Path(result["report_result_path"]).exists()
    assert Path(result["report_html_path"]).exists()
    assert result["dashboard_payload"]


def test_run_report_agent_from_run_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "results" / "runs" / "previous_run"
    context = fake_context()
    write_json(run_dir / "project_info.json", context["project_info"])
    write_json(run_dir / "test_plan.json", context["test_plan"])
    write_json(run_dir / "api_result.json", context["api_results"])
    write_json(run_dir / "bug_result.json", context["bug_results"])

    result = run_report_agent_alone(run_dir=str(run_dir))

    assert result["run_id"] == "previous_run"
    assert Path(result["final_results_path"]).exists()
    assert Path(result["report_html_path"]).exists()


def test_report_node_returns_state_patch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    update = report_node(fake_context())

    assert update["final_results"]
    assert update["final_results_path"]
    assert update["report_result_path"]
    assert update["report_html_path"]
    assert update["dashboard_payload"]
    assert update["agent_logs"]


def test_report_agent_handles_missing_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_report_agent_alone(context={})

    assert result["final_results"]["status"] == "partial"
    assert Path(result["report_html_path"]).exists()


def test_report_agent_does_not_expose_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    context = fake_context()
    context["api_results"]["tests"][0]["details"] = "Bearer SECRET_TOKEN_SHOULD_NOT_APPEAR"
    context["user_preferences"] = {"auth_token": "SECRET_TOKEN_SHOULD_NOT_APPEAR"}

    result = run_report_agent_alone(context=context)

    final_text = Path(result["final_results_path"]).read_text(encoding="utf-8")
    report_text = Path(result["report_result_path"]).read_text(encoding="utf-8")
    html_text = Path(result["report_html_path"]).read_text(encoding="utf-8")
    assert "SECRET_TOKEN_SHOULD_NOT_APPEAR" not in final_text
    assert "SECRET_TOKEN_SHOULD_NOT_APPEAR" not in report_text
    assert "SECRET_TOKEN_SHOULD_NOT_APPEAR" not in html_text


def test_cli_helpers_if_present(tmp_path: Path) -> None:
    run_dir = tmp_path / "results" / "runs" / "helper_run"
    write_json(run_dir / "api_result.json", {"summary": {"total_tests": 0}})

    context = load_report_context_from_run_dir(str(run_dir))

    assert context["run_id"] == "helper_run"
    assert context["api_results"]["summary"]["total_tests"] == 0
