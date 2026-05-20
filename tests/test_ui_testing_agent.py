from __future__ import annotations

import json
from pathlib import Path

from test_auto.agents import ui_testing_agent
from test_auto.agents.ui_testing_agent import (
    extract_ui_tests,
    normalize_ui_test_case,
    run_ui_testing_agent_alone,
    ui_testing_node,
)


def fake_ui_plan() -> dict:
    return {
        "ui_tests": [
            {
                "id": "UI_001",
                "name": "login_page_visible",
                "flow": "login",
                "steps": ["open login page"],
                "expected_result": "login form is visible",
                "evidence_sources": ["templates/login.html"],
            }
        ]
    }


def mocked_ui_result(target_url, test_case, run_id, discovered_ui_flows=None, user_preferences=None):
    return {
        "id": test_case.get("id", "UI_001"),
        "name": test_case.get("name", "login_page_visible"),
        "flow": test_case.get("flow"),
        "status": "passed",
        "target_path": "/login/",
        "target_url": f"{target_url.rstrip('/')}/login/",
        "duration_ms": 5.0,
        "details": "mocked",
        "screenshot": None,
        "assertions": [{"type": "login_form_present", "passed": True}],
        "error_type": None,
        "evidence": {"title": "Login"},
    }


def test_extract_ui_tests() -> None:
    assert len(extract_ui_tests(fake_ui_plan())) == 1


def test_run_ui_testing_agent_alone_no_ui_tests(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_ui_testing_agent_alone(
        target_url="http://localhost:8000",
        test_plan={},
        run_id="ui_no_tests",
    )

    assert result["ui_results"]["status"] == "partial"
    assert Path(result["ui_result_path"]).exists()


def test_run_ui_testing_agent_alone_with_mocked_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ui_testing_agent, "execute_ui_test_case", mocked_ui_result)

    result = run_ui_testing_agent_alone(
        target_url="http://localhost:8000",
        test_plan=fake_ui_plan(),
        run_id="ui_mocked",
    )

    assert result["run_id"] == "ui_mocked"
    assert result["ui_results"]
    assert Path(result["ui_result_path"]).exists()
    assert result["summary"]["total_tests"] == 1


def test_ui_testing_node_returns_state_patch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ui_testing_agent, "execute_ui_test_case", mocked_ui_result)

    patch = ui_testing_node(
        {
            "run_id": "test_run",
            "target_url": "http://localhost:8000",
            "test_plan": fake_ui_plan(),
            "user_preferences": {},
            "errors": [],
            "agent_logs": [],
        }
    )

    assert patch["ui_results"]
    assert patch["ui_result_path"]
    assert "screenshots" in patch
    assert patch["agent_logs"]


def test_ui_testing_node_missing_target_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    patch = ui_testing_node(
        {
            "run_id": "missing_target",
            "target_url": "",
            "test_plan": fake_ui_plan(),
            "user_preferences": {},
            "errors": [],
            "agent_logs": [],
        }
    )

    assert patch["ui_results"]["status"] == "error"
    assert patch["errors"]


def test_ui_agent_does_not_expose_password_or_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_ui_testing_agent_alone(
        target_url="http://localhost:8000",
        test_plan={},
        run_id="ui_secret_masking",
        user_preferences={
            "password": "PASSWORD_SHOULD_NOT_APPEAR",
            "token": "TOKEN_SHOULD_NOT_APPEAR",
        },
    )

    payload = json.dumps(result)
    assert "PASSWORD_SHOULD_NOT_APPEAR" not in payload
    assert "TOKEN_SHOULD_NOT_APPEAR" not in payload


def test_normalize_ui_test_case_adds_login_form_assertion() -> None:
    normalized = normalize_ui_test_case(
        {
            "id": "UI_001",
            "name": "login_page_visible",
            "flow": "login",
            "expected_result": "login form is visible",
        }
    )

    assert normalized["assertions"][0]["type"] == "login_form_present"
