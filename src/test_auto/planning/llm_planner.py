"""LLM-backed planning with deterministic fallback."""

from __future__ import annotations

import json
from typing import Any

from test_auto.planning.deterministic_planner import generate_deterministic_test_plan
from test_auto.planning.prompt_builder import build_test_planner_messages
from test_auto.shared.schemas import ASSERTION_TYPES, TEST_CATEGORIES, TEST_PRIORITIES, TestPlan
from test_auto.shared.secrets import get_env_value, get_llm_config


def get_planner_llm_config() -> dict[str, Any]:
    """Return non-secret planner LLM availability metadata."""

    config = get_llm_config()
    provider = str(config.get("provider") or "none").lower()
    if provider not in {"groq", "mistral"}:
        return {"provider": "none", "model": None, "available": False}

    if provider == "groq":
        return {
            "provider": "groq",
            "model": config.get("groq_model"),
            "available": bool(config.get("has_groq_key") and config.get("groq_model")),
        }
    return {
        "provider": "mistral",
        "model": config.get("mistral_model"),
        "available": bool(config.get("has_mistral_key") and config.get("mistral_model")),
    }


def is_llm_planning_available() -> bool:
    """Return True only when provider, model, and key presence are configured."""

    return bool(get_planner_llm_config().get("available"))


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


def _normalize_llm_test_plan(raw_plan: dict[str, Any]) -> dict[str, Any]:
    """Repair common LLM JSON shape drift before Pydantic validation."""

    plan = dict(raw_plan or {})
    plan.setdefault("scope", "LLM-generated test plan")
    plan.setdefault("assumptions", [])
    plan.setdefault("api_tests", [])
    plan.setdefault("ui_tests", [])
    plan.setdefault("performance_tests", [])
    plan.setdefault("excluded_tests", [])
    plan.setdefault("missing_information", [])
    plan.setdefault("risks", [])
    plan.setdefault("reasoning_summary", "LLM generated a grounded test plan.")

    assertion_type_aliases = {
        "body_contains": "response_contains",
        "json_body": "response_schema",
        "response_body": "response_contains",
        "schema": "response_schema",
        "text_contains": "response_contains",
    }
    category_aliases = {
        "functionality": "functional",
        "happy_path": "functional",
        "authorization": "security",
        "authentication": "security",
        "auth": "security",
        "error": "negative",
    }
    priority_aliases = {
        "critical": "high",
        "important": "high",
        "normal": "medium",
        "minor": "low",
    }
    for test_case in plan.get("api_tests") or []:
        if not isinstance(test_case, dict):
            continue
        category = str(test_case.get("category") or "functional").strip().lower()
        test_case["category"] = category_aliases.get(category, category)
        if test_case["category"] not in TEST_CATEGORIES:
            test_case["category"] = "functional"
        priority = str(test_case.get("priority") or "medium").strip().lower()
        test_case["priority"] = priority_aliases.get(priority, priority)
        if test_case["priority"] not in TEST_PRIORITIES:
            test_case["priority"] = "medium"
        repaired_assertions: list[dict[str, Any]] = []
        for assertion in test_case.get("assertions") or []:
            if not isinstance(assertion, dict):
                continue
            assertion_type = str(assertion.get("type") or "custom").strip()
            assertion_type = assertion_type_aliases.get(assertion_type, assertion_type)
            if assertion_type not in ASSERTION_TYPES:
                assertion_type = "custom"
            expected = assertion.get("expected")
            if expected is None:
                expected = assertion.get("description") or assertion.get("target") or "expected behavior"
            repaired_assertions.append(
                {
                    "type": assertion_type,
                    "expected": str(expected),
                    "target": assertion.get("target"),
                }
            )
        test_case["assertions"] = repaired_assertions

    return plan


def generate_llm_test_plan(
    context: dict[str, Any],
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Generate a TestPlan with Groq or Mistral when safely configured."""

    config = get_planner_llm_config()
    if not config["available"]:
        raise RuntimeError("LLM planning is not available.")

    provider = config["provider"]
    model = config["model"]
    messages = build_test_planner_messages(context)
    try:
        if provider == "groq":
            from langchain_groq import ChatGroq

            llm = ChatGroq(
                api_key=get_env_value("GROQ_API_KEY"),
                model=model,
                temperature=0,
                timeout=timeout_seconds,
            )
        elif provider == "mistral":
            from langchain_mistralai import ChatMistralAI

            llm = ChatMistralAI(
                api_key=get_env_value("MISTRAL_API_KEY"),
                model=model,
                temperature=0,
                timeout=timeout_seconds,
            )
        else:
            raise RuntimeError("Unsupported LLM provider.")
    except Exception as error:
        raise RuntimeError(f"Planner LLM dependency or setup failed: {error.__class__.__name__}")

    try:
        response = llm.invoke(messages)
        content = getattr(response, "content", response)
        parsed = _extract_json(str(content))
        parsed = _normalize_llm_test_plan(parsed)
        return TestPlan(**parsed).model_dump(mode="json")
    except Exception as error:
        raise RuntimeError(f"LLM planning failed: {error.__class__.__name__}")


def plan_with_llm_or_fallback(
    context: dict[str, Any],
    fallback_inputs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Try the configured LLM planner, then fall back deterministically on error."""

    config = get_planner_llm_config()
    if config["available"]:
        try:
            test_plan = generate_llm_test_plan(context)
            return (
                test_plan,
                {
                    "mode": "llm",
                    "provider": config["provider"],
                    "model": config["model"],
                },
            )
        except Exception as error:
            fallback_reason = f"{error.__class__.__name__}; deterministic fallback used."
    else:
        fallback_reason = "LLM provider/model/key not configured."

    test_plan = generate_deterministic_test_plan(**fallback_inputs)
    return (
        test_plan,
        {
            "mode": "deterministic_fallback",
            "provider": "none",
            "model": None,
            "reason": fallback_reason,
        },
    )
