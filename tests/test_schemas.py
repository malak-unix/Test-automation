from __future__ import annotations

import pytest
from pydantic import ValidationError

from test_auto.shared.schemas import (
    AgentOutput,
    AgentSummary,
    AgentTestResult,
    OrchestratorDecision,
)


def test_agent_output_accepts_valid_data() -> None:
    output = AgentOutput(
        agent="orchestrator",
        timestamp="2026-05-19T00:00:00+00:00",
        status="success",
        duration_seconds=0.1,
        summary=AgentSummary(total_tests=1, passed=1, failed=0, pass_rate=100.0),
        tests=[AgentTestResult(name="request_validation", status="passed")],
        anomalies=[],
        metadata={},
    )

    assert output.status == "success"


def test_agent_output_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        AgentOutput(
            agent="orchestrator",
            timestamp="2026-05-19T00:00:00+00:00",
            status="ok",
            duration_seconds=0.1,
            summary=AgentSummary(),
        )


def test_agent_test_result_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        AgentTestResult(name="bad_status", status="unknown")


def test_orchestrator_decision_accepts_valid_selected_agents() -> None:
    decision = OrchestratorDecision(
        run_id="run_123",
        selected_agents=["repository_analyzer", "rag", "test_planner", "api", "bug", "report"],
        execution_mode="sequential",
        reasoning_summary="valid",
        risks=[],
        next_node="repository_analyzer",
    )

    assert "api" in decision.selected_agents


def test_orchestrator_decision_rejects_invalid_selected_agents() -> None:
    with pytest.raises(ValidationError):
        OrchestratorDecision(
            run_id="run_123",
            selected_agents=["repository_analyzer", "unknown_agent"],
            execution_mode="sequential",
            reasoning_summary="invalid",
            risks=[],
            next_node="repository_analyzer",
        )


def test_orchestrator_decision_rejects_invalid_execution_mode() -> None:
    with pytest.raises(ValidationError):
        OrchestratorDecision(
            run_id="run_123",
            selected_agents=["api"],
            execution_mode="distributed",
            reasoning_summary="invalid",
            risks=[],
            next_node="api",
        )
