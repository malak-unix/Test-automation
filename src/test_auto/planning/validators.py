"""Validation helpers for grounding Test Planner output in evidence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from test_auto.shared.schemas import TestPlan
from test_auto.shared.utils import ensure_directory, write_json_file


def _normalize(path: str) -> str:
    normalized = re.sub(r"/+", "/", str(path or "").strip())
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def collect_allowed_endpoints(discovered_endpoints: list[dict[str, Any]]) -> set[str]:
    """Collect normalized endpoint paths from Repository Analyzer evidence."""

    return {_normalize(str(item.get("path", ""))) for item in discovered_endpoints if item.get("path")}


def _allowed_sources(
    discovered_endpoints: list[dict[str, Any]],
    retrieved_context: list[dict[str, Any]],
) -> set[str]:
    sources = {
        str(item.get("source_file"))
        for item in discovered_endpoints
        if item.get("source_file")
    }
    sources.update(
        str(item.get("source_path"))
        for item in retrieved_context
        if item.get("source_path")
    )
    return sources


def _all_planned_tests(test_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *test_plan.get("api_tests", []),
        *test_plan.get("ui_tests", []),
        *test_plan.get("performance_tests", []),
    ]


def validate_test_plan_against_evidence(
    test_plan: dict[str, Any],
    discovered_endpoints: list[dict[str, Any]],
    retrieved_context: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check that planned endpoints and evidence sources are grounded."""

    issues: list[str] = []
    try:
        plan = TestPlan(**test_plan).model_dump(mode="json")
    except Exception as error:
        return {"is_valid": False, "issues": [str(error)]}

    allowed_endpoints = collect_allowed_endpoints(discovered_endpoints)
    allowed_sources = _allowed_sources(discovered_endpoints, retrieved_context)

    for item in plan.get("api_tests", []):
        endpoint = _normalize(item.get("endpoint", ""))
        if endpoint not in allowed_endpoints:
            issues.append(f"API test {item.get('id')} uses undiscovered endpoint {endpoint}.")

    for item in _all_planned_tests(plan):
        sources = [source for source in item.get("evidence_sources", []) if source]
        if not sources:
            issues.append(f"Planned test {item.get('id')} has no evidence_sources.")
            continue
        if allowed_sources and not any(source in allowed_sources for source in sources):
            issues.append(
                f"Planned test {item.get('id')} has no evidence source from endpoints or retrieved context."
            )

    return {"is_valid": not issues, "issues": issues}


def repair_or_filter_invalid_test_plan(
    test_plan: dict[str, Any],
    discovered_endpoints: list[dict[str, Any]],
    retrieved_context: list[dict[str, Any]],
) -> dict[str, Any]:
    """Remove invented endpoint plans and record what was filtered."""

    plan = TestPlan(**test_plan).model_dump(mode="json")
    allowed_endpoints = collect_allowed_endpoints(discovered_endpoints)
    kept_api_tests = []
    removed = []
    for item in plan.get("api_tests", []):
        endpoint = _normalize(item.get("endpoint", ""))
        if endpoint in allowed_endpoints:
            kept_api_tests.append(item)
        else:
            removed.append(f"Removed {item.get('id')} because {endpoint} was not discovered.")

    allowed_sources = _allowed_sources(discovered_endpoints, retrieved_context)
    fallback_source = next(iter(allowed_sources), "")
    for collection_name in ("ui_tests", "performance_tests"):
        for item in plan.get(collection_name, []):
            if not item.get("evidence_sources") and fallback_source:
                item["evidence_sources"] = [fallback_source]

    plan["api_tests"] = kept_api_tests
    if removed:
        plan["missing_information"] = sorted(
            set([*plan.get("missing_information", []), *removed])
        )
    return TestPlan(**plan).model_dump(mode="json")


def save_test_plan(
    run_id: str,
    test_plan: dict[str, Any],
    results_dir: str = "results",
) -> str:
    """Save results/runs/<run_id>/test_plan.json."""

    run_dir = ensure_directory(Path(results_dir) / "runs" / run_id)
    path = write_json_file(run_dir / "test_plan.json", test_plan)
    return str(path)

