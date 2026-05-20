from __future__ import annotations

from pathlib import Path
from typing import Any

from test_auto.agents.orchestrator import (
    build_orchestrator_decision,
    build_selected_agents,
    normalize_test_types,
    orchestrator_node,
    run_orchestrator_alone,
)
from test_auto.graph.state import TestAutomationState


def make_state(**overrides: Any) -> TestAutomationState:
    state: TestAutomationState = {
        "run_id": "",
        "repo_url": "https://github.com/example/todo-app",
        "target_url": "http://localhost:8000",
        "user_preferences": {
            "test_types": ["api"],
            "execution_mode": "sequential",
            "max_duration_minutes": 5,
        },
        "selected_agents": [],
        "orchestrator_decision": {},
        "errors": [],
        "agent_logs": [],
    }
    state.update(overrides)
    return state


def test_default_test_types_becomes_api() -> None:
    assert normalize_test_types(None) == ["api"]


def test_api_selection_includes_api() -> None:
    assert "api" in build_selected_agents(["api"])


def test_ui_selection_includes_ui() -> None:
    assert "ui" in build_selected_agents(["ui"])


def test_performance_selection_includes_performance() -> None:
    assert "performance" in build_selected_agents(["performance"])


def test_future_pipeline_agents_are_always_included() -> None:
    selected = build_selected_agents(["api"])

    for agent_name in ["repository_analyzer", "rag", "test_planner", "bug", "report"]:
        assert agent_name in selected


def test_invalid_target_url_adds_error(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    update = orchestrator_node(make_state(target_url="not-a-url"))

    assert any(error["field"] == "target_url" for error in update["errors"])


def test_invalid_repo_url_adds_error(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    update = orchestrator_node(make_state(repo_url="not-a-url"))

    assert any(error["field"] == "repo_url" for error in update["errors"])


def test_invalid_execution_mode_defaults_to_sequential_and_adds_risk() -> None:
    state = make_state(
        user_preferences={
            "test_types": ["api"],
            "execution_mode": "fast",
            "max_duration_minutes": 5,
        }
    )

    decision = build_orchestrator_decision(state)

    assert decision.execution_mode == "sequential"
    assert decision.risks


def test_run_id_is_generated(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    update = orchestrator_node(make_state())

    assert update["run_id"].startswith("run_")


def test_orchestrator_node_returns_partial_state_update(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    update = orchestrator_node(make_state())

    assert set(update) == {
        "run_id",
        "selected_agents",
        "orchestrator_decision",
        "agent_logs",
        "errors",
    }


def test_run_orchestrator_alone_returns_structured_data(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_orchestrator_alone(
        repo_url="https://github.com/example/todo-app",
        target_url="http://localhost:8000",
        user_preferences={
            "test_types": ["api", "ui"],
            "execution_mode": "parallel",
            "max_duration_minutes": 5,
        },
    )

    assert "orchestrator_decision" in result
    assert result["orchestrator_decision"]["execution_mode"] == "parallel"


def test_orchestrator_result_json_is_saved(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_orchestrator_alone(
        repo_url="https://github.com/example/todo-app",
        target_url="http://localhost:8000",
        user_preferences={"test_types": ["api"], "execution_mode": "sequential"},
    )
    result_path = (
        Path("results")
        / "runs"
        / result["run_id"]
        / "orchestrator_result.json"
    )

    assert result_path.exists()
