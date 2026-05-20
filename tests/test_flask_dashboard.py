from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_auto.interface.flask_app import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(testing=True)
    return app.test_client()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_health_route(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_index_route(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert b"Run Test Automation" in response.data


def test_recent_runs_route(client) -> None:
    response = client.get("/runs")

    assert response.status_code == 200
    assert b"Recent Runs" in response.data


def test_run_route_with_mocked_workflow(client, monkeypatch) -> None:
    def fake_run_and_summarize(form_data):
        return {
            "status": "success",
            "summary": {
                "run_id": "mock_run",
                "status": "success",
                "selected_agents": ["report"],
                "framework": "Django REST Framework",
                "target_url": "http://localhost:8000",
                "global_score": 95,
                "api_summary": {"total_tests": 1, "pass_rate": 100.0},
                "bug_summary": {"total_anomalies": 0, "high": 0},
                "recommendation_count": 0,
                "errors": [],
            },
            "report_html": "<h1>Mock Report</h1>",
        }

    monkeypatch.setattr(
        "test_auto.interface.flask_app.run_service.run_and_summarize",
        fake_run_and_summarize,
    )
    response = client.post(
        "/run",
        data={"repo_url": "https://github.com/example/repo", "target_url": "http://localhost:8000"},
    )

    assert response.status_code == 200
    assert b"mock_run" in response.data
    assert b"Mock Report" in response.data


def test_run_route_handles_error(client, monkeypatch) -> None:
    def fake_run_and_summarize(form_data):
        return {
            "status": "error",
            "error": "Workflow failed safely.",
            "errors": [{"agent": "dashboard", "field": "workflow", "message": "bad input"}],
        }

    monkeypatch.setattr(
        "test_auto.interface.flask_app.run_service.run_and_summarize",
        fake_run_and_summarize,
    )
    response = client.post("/run", data={"target_url": "http://localhost:8000"})

    assert response.status_code == 500
    assert b"Workflow failed safely" in response.data


def test_view_run_route_with_fake_run(client) -> None:
    run_id = "dashboard_view_run"
    write_json(
        Path("results") / "runs" / run_id / "final_results.json",
        {
            "status": "success",
            "target_url": "http://localhost:8000",
            "project_info": {"framework": "Django REST Framework"},
            "api_summary": {"total_tests": 1, "pass_rate": 100.0},
            "bug_summary": {"total_anomalies": 0},
            "kpis": {
                "global_score": 100.0,
                "pass_rate": 100.0,
                "total_api_tests": 1,
                "total_anomalies": 0,
                "recommendation_count": 0,
            },
            "artifact_paths": {"report_html_path": f"reports/generated/report_{run_id}.html"},
            "limitations": [],
        },
    )
    report_path = Path("reports") / "generated" / f"report_{run_id}.html"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("<h1>Saved Report</h1>", encoding="utf-8")

    response = client.get(f"/runs/{run_id}")

    assert response.status_code == 200
    assert b"dashboard_view_run" in response.data
    assert b"Saved Report" in response.data


def test_view_run_rejects_path_traversal(client) -> None:
    response = client.get("/runs/..%2F..%2Fsecret")

    assert response.status_code == 404


def test_dashboard_does_not_expose_token(client, monkeypatch) -> None:
    token = "SECRET_TOKEN_SHOULD_NOT_APPEAR"

    def fake_run_and_summarize(form_data):
        return {
            "status": "success",
            "summary": {
                "run_id": "masked_run",
                "status": "success",
                "selected_agents": ["report"],
                "framework": "Django REST Framework",
                "target_url": "http://localhost:8000",
                "global_score": 100,
                "api_summary": {"total_tests": 1, "pass_rate": 100.0},
                "bug_summary": {"total_anomalies": 0, "high": 0},
                "recommendation_count": 0,
                "errors": [],
            },
            "report_html": "<p>Bearer ***MASKED***</p>",
        }

    monkeypatch.setattr(
        "test_auto.interface.flask_app.run_service.run_and_summarize",
        fake_run_and_summarize,
    )
    response = client.post("/run", data={"target_url": "http://localhost:8000"})

    assert token.encode() not in response.data
