from __future__ import annotations

from test_auto.planning.deterministic_planner import generate_deterministic_test_plan
from test_auto.planning.validators import (
    repair_or_filter_invalid_test_plan,
    validate_test_plan_against_evidence,
)


def project_info() -> dict:
    return {
        "language": "Python",
        "framework": "Django REST Framework",
        "has_api": True,
        "has_ui": True,
        "auth_type": "JWT",
    }


def endpoints() -> list[dict]:
    return [
        {
            "method": "UNKNOWN",
            "path": "/api/todos/",
            "source_file": "todo/urls.py",
        }
    ]


def retrieved_context() -> list[dict]:
    return [
        {
            "source_path": "README.md",
            "content": "JWT authentication is required for Todo CRUD API operations.",
            "score": 0.9,
            "reason": "JWT and CRUD evidence",
            "chunk_type": "doc",
        }
    ]


def test_generate_deterministic_plan_from_endpoints() -> None:
    plan = generate_deterministic_test_plan(
        project_info(),
        endpoints(),
        [],
        retrieved_context(),
        {"test_types": ["api"]},
    )

    assert plan["api_tests"]


def test_plan_does_not_invent_endpoints() -> None:
    plan = generate_deterministic_test_plan(
        project_info(),
        endpoints(),
        [],
        retrieved_context(),
        {"test_types": ["api"]},
    )

    assert {test["endpoint"] for test in plan["api_tests"]} == {"/api/todos/"}


def test_jwt_context_creates_security_test() -> None:
    plan = generate_deterministic_test_plan(
        project_info(),
        endpoints(),
        [],
        retrieved_context(),
        {"test_types": ["api"]},
    )

    assert any(test["category"] == "security" for test in plan["api_tests"])


def test_ui_flow_creates_ui_test() -> None:
    plan = generate_deterministic_test_plan(
        project_info(),
        endpoints(),
        [
            {
                "name": "login",
                "source_file": "templates/login.html",
                "flow_type": "authentication",
            }
        ],
        retrieved_context(),
        {"test_types": ["ui"]},
    )

    assert plan["ui_tests"]


def test_performance_created_only_when_requested() -> None:
    without_perf = generate_deterministic_test_plan(
        project_info(),
        endpoints(),
        [],
        retrieved_context(),
        {"test_types": ["api"]},
    )
    with_perf = generate_deterministic_test_plan(
        project_info(),
        endpoints(),
        [],
        retrieved_context(),
        {"test_types": ["api", "performance"]},
    )

    assert without_perf["performance_tests"] == []
    assert with_perf["performance_tests"]


def test_validate_test_plan_against_evidence() -> None:
    plan = generate_deterministic_test_plan(
        project_info(),
        endpoints(),
        [],
        retrieved_context(),
        {"test_types": ["api"]},
    )
    invalid = {
        **plan,
        "api_tests": [
            {
                **plan["api_tests"][0],
                "endpoint": "/invented/",
            }
        ],
    }

    assert validate_test_plan_against_evidence(plan, endpoints(), retrieved_context())[
        "is_valid"
    ]
    assert not validate_test_plan_against_evidence(
        invalid,
        endpoints(),
        retrieved_context(),
    )["is_valid"]


def test_repair_or_filter_invalid_test_plan_removes_invented_endpoint() -> None:
    plan = generate_deterministic_test_plan(
        project_info(),
        endpoints(),
        [],
        retrieved_context(),
        {"test_types": ["api"]},
    )
    plan["api_tests"].append({**plan["api_tests"][0], "id": "API_BAD", "endpoint": "/invented/"})

    repaired = repair_or_filter_invalid_test_plan(plan, endpoints(), retrieved_context())

    assert all(test["endpoint"] != "/invented/" for test in repaired["api_tests"])
    assert repaired["missing_information"]

