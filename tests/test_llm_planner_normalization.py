from __future__ import annotations

from test_auto.planning.llm_planner import _normalize_llm_test_plan
from test_auto.shared.schemas import TestPlan as PlanSchema


def test_normalize_llm_test_plan_repairs_common_llm_shape_drift() -> None:
    raw_plan = {
        "scope": "JWT authentication tests",
        "assumptions": [{"item": "Target app is running."}],
        "api_tests": [],
        "ui_tests": [
            {
                "id": "UI_001",
                "name": "login_page_renders",
                "flow_name": "login",
                "objective": "Ensure the login page loads.",
                "priority": "important",
                "steps": ["Navigate to /login/"],
                "assertions": [{"type": "element_present", "target": "form"}],
                "evidence_sources": [{"name": "templates/login.html"}],
            }
        ],
        "performance_tests": [
            {
                "id": "PERF_001",
                "name": "baseline",
                "objective": "Measure baseline latency.",
                "evidence_sources": [{"reason": "GET endpoint"}],
            }
        ],
        "excluded_tests": [{"reason": "Mutating methods are disabled."}],
        "missing_information": [{"item": "Credentials are not provided."}],
        "risks": [{"message": "Selectors may need adjustment."}],
        "reasoning_summary": "LLM produced a grounded plan.",
    }

    normalized = _normalize_llm_test_plan(raw_plan)
    validated = PlanSchema(**normalized)

    assert validated.assumptions == ["Target app is running."]
    assert validated.ui_tests[0].flow == "login"
    assert validated.ui_tests[0].expected_result == "form"
    assert validated.ui_tests[0].priority == "high"
    assert validated.performance_tests[0].endpoint == "/"
    assert validated.excluded_tests == ["Mutating methods are disabled."]
    assert validated.missing_information == ["Credentials are not provided."]
