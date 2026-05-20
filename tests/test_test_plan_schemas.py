from __future__ import annotations

import pytest
from pydantic import ValidationError

from test_auto.shared.schemas import (
    APITestCasePlan,
    TestPlan as PlanSchema,
    TestPlanAssertion as PlanAssertionSchema,
    TestPlannerOutput as PlannerOutputSchema,
)
from test_auto.shared.utils import current_timestamp


def valid_api_test() -> dict:
    return {
        "id": "API_001",
        "name": "todo_list_smoke",
        "method": "GET",
        "endpoint": "/api/todos/",
        "objective": "Verify todo list endpoint exists.",
        "assertions": [{"type": "status_code", "expected": "200"}],
        "evidence_sources": ["todo/urls.py"],
    }


def test_valid_test_plan_schema() -> None:
    plan = PlanSchema(
        scope="Todo API",
        api_tests=[valid_api_test()],
        reasoning_summary="Plan is grounded in discovered endpoint evidence.",
    )

    assert plan.api_tests[0].endpoint == "/api/todos/"


def test_invalid_api_method_rejected() -> None:
    with pytest.raises(ValidationError):
        APITestCasePlan(**{**valid_api_test(), "method": "FETCH"})


def test_invalid_priority_rejected() -> None:
    with pytest.raises(ValidationError):
        APITestCasePlan(**{**valid_api_test(), "priority": "urgent"})


def test_test_plan_requires_reasoning_summary() -> None:
    with pytest.raises(ValidationError):
        PlanSchema(scope="Todo API", api_tests=[valid_api_test()], reasoning_summary="")


def test_retrieved_test_plan_output_schema() -> None:
    output = PlannerOutputSchema(
        timestamp=current_timestamp(),
        status="success",
        duration_seconds=0.1,
        test_plan=PlanSchema(
            scope="Todo API",
            api_tests=[valid_api_test()],
            reasoning_summary="Plan is grounded in discovered endpoint evidence.",
        ),
        model_info={"mode": "deterministic_fallback", "provider": "none"},
    )

    assert output.agent == "test_planner"
    assert PlanAssertionSchema(type="custom", expected="ok")
