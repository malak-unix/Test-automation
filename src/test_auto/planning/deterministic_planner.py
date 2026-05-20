"""Deterministic fallback planner used when no LLM is configured."""

from __future__ import annotations

import re
from typing import Any

from test_auto.shared.schemas import TestPlan


CRUD_KEYWORDS = {"todo", "task", "crud", "create", "update", "delete"}
AUTH_KEYWORDS = {"jwt", "auth", "authentication", "token", "login"}


def normalize_endpoint_path(path: str) -> str:
    """Normalize endpoint paths while preserving Django path parameters."""

    if not path:
        return "/"
    normalized = re.sub(r"/+", "/", path.strip())
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def _context_text(retrieved_context: list[dict[str, Any]]) -> str:
    return " ".join(str(item.get("content", "")) for item in retrieved_context).lower()


def _context_sources(
    retrieved_context: list[dict[str, Any]],
    limit: int = 2,
) -> list[str]:
    sources: list[str] = []
    for item in retrieved_context:
        source = item.get("source_path")
        if source and source not in sources:
            sources.append(source)
        if len(sources) >= limit:
            break
    return sources


def _evidence_sources(
    source_file: str | None,
    retrieved_context: list[dict[str, Any]],
) -> list[str]:
    sources = []
    if source_file:
        sources.append(source_file)
    for source in _context_sources(retrieved_context):
        if source not in sources:
            sources.append(source)
    return sources


def infer_auth_required(
    project_info: dict[str, Any],
    endpoint: dict[str, Any],
    retrieved_context: list[dict[str, Any]],
) -> bool:
    """Infer whether an endpoint likely requires authentication from evidence."""

    path = str(endpoint.get("path", "")).lower()
    if any(term in path for term in ("login", "token", "auth", "register", "signup")):
        return False
    if str(project_info.get("auth_type", "")).upper() == "JWT":
        return True
    context = _context_text(retrieved_context)
    return any(keyword in context for keyword in AUTH_KEYWORDS)


def _has_crud_evidence(
    endpoint: dict[str, Any],
    retrieved_context: list[dict[str, Any]],
) -> bool:
    text = f"{endpoint.get('path', '')} {_context_text(retrieved_context)}".lower()
    return any(keyword in text for keyword in CRUD_KEYWORDS)


def _status_assertion(status: int | None) -> list[dict[str, str]]:
    if status is None:
        return [{"type": "custom", "expected": "Endpoint responds according to implementation."}]
    return [{"type": "status_code", "expected": str(status)}]


def build_api_tests_from_endpoints(
    project_info: dict[str, Any],
    discovered_endpoints: list[dict[str, Any]],
    retrieved_context: list[dict[str, Any]],
    user_preferences: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Create a small grounded API test plan from discovered endpoints."""

    tests: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for endpoint in discovered_endpoints:
        path = normalize_endpoint_path(str(endpoint.get("path", "")))
        method = str(endpoint.get("method") or "UNKNOWN").upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "UNKNOWN"}:
            method = "UNKNOWN"
        source_file = endpoint.get("source_file")
        evidence = _evidence_sources(source_file, retrieved_context)
        auth_required = infer_auth_required(project_info, endpoint, retrieved_context)
        crud_evidence = _has_crud_evidence(endpoint, retrieved_context)

        if method in {"GET", "UNKNOWN"}:
            key = ("smoke", method, path)
            if key not in seen:
                expected_status = 200 if method == "GET" else None
                tests.append(
                    {
                        "id": f"API_{len(tests) + 1:03d}",
                        "name": f"smoke_{path.strip('/').replace('/', '_') or 'root'}",
                        "method": method,
                        "endpoint": path,
                        "objective": f"Verify the discovered endpoint {path} is reachable according to repository evidence.",
                        "priority": "high" if "api" in path.lower() else "medium",
                        "category": "smoke",
                        "auth_required": auth_required,
                        "expected_status": expected_status,
                        "assertions": _status_assertion(expected_status),
                        "evidence_sources": evidence,
                        "risks": ["Expected status may need refinement when executable tests are added."]
                        if expected_status is None
                        else [],
                    }
                )
                seen.add(key)

            if auth_required:
                key = ("unauthenticated", method, path)
                if key not in seen:
                    tests.append(
                        {
                            "id": f"API_{len(tests) + 1:03d}",
                            "name": f"unauthenticated_access_rejected_{path.strip('/').replace('/', '_') or 'root'}",
                            "method": "GET" if method == "UNKNOWN" else method,
                            "endpoint": path,
                            "objective": f"Verify unauthenticated access to {path} is rejected when JWT protection is evidenced.",
                            "priority": "high",
                            "category": "security",
                            "auth_required": False,
                            "expected_status": 401,
                            "assertions": [
                                {"type": "status_code", "expected": "401"},
                                {
                                    "type": "security_expectation",
                                    "expected": "Unauthenticated request should not expose protected data.",
                                },
                            ],
                            "evidence_sources": evidence,
                            "risks": [],
                        }
                    )
                    seen.add(key)

        if method == "POST":
            tests.append(
                {
                    "id": f"API_{len(tests) + 1:03d}",
                    "name": f"create_resource_{path.strip('/').replace('/', '_') or 'root'}",
                    "method": "POST",
                    "endpoint": path,
                    "objective": f"Verify a valid create request for {path} follows repository API evidence.",
                    "priority": "medium",
                    "category": "functional",
                    "auth_required": auth_required,
                    "request_body": {},
                    "expected_status": 201 if crud_evidence else None,
                    "assertions": _status_assertion(201 if crud_evidence else None),
                    "evidence_sources": evidence,
                    "risks": ["Request body fields are not known yet; future agents must derive them before execution."],
                }
            )
            tests.append(
                {
                    "id": f"API_{len(tests) + 1:03d}",
                    "name": f"missing_required_fields_rejected_{path.strip('/').replace('/', '_') or 'root'}",
                    "method": "POST",
                    "endpoint": path,
                    "objective": f"Verify incomplete create requests for {path} are rejected.",
                    "priority": "medium",
                    "category": "negative",
                    "auth_required": auth_required,
                    "request_body": {},
                    "expected_status": 400,
                    "assertions": [{"type": "status_code", "expected": "400"}],
                    "evidence_sources": evidence,
                    "risks": ["Required fields are not identified in this milestone."],
                }
            )

        if method in {"PUT", "PATCH", "DELETE"}:
            status = 204 if method == "DELETE" else 200
            tests.append(
                {
                    "id": f"API_{len(tests) + 1:03d}",
                    "name": f"{method.lower()}_{path.strip('/').replace('/', '_') or 'root'}",
                    "method": method,
                    "endpoint": path,
                    "objective": f"Verify {method} behavior for the discovered endpoint {path}.",
                    "priority": "medium",
                    "category": "functional",
                    "auth_required": auth_required,
                    "expected_status": status,
                    "assertions": [{"type": "status_code", "expected": str(status)}],
                    "evidence_sources": evidence,
                    "risks": ["Exact payload or resource setup is deferred to later executable agents."],
                }
            )

        if len(tests) >= 8:
            break

    return tests[:8]


def build_ui_tests_from_flows(
    discovered_ui_flows: list[dict[str, Any]],
    retrieved_context: list[dict[str, Any]],
    user_preferences: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Create high-level UI test plans from discovered UI flows."""

    tests: list[dict[str, Any]] = []
    for flow in discovered_ui_flows:
        name = str(flow.get("name", "")).lower()
        if not name:
            continue
        if name not in {"login", "register", "signup", "dashboard", "todo", "task"}:
            continue
        sources = _evidence_sources(flow.get("source_file"), retrieved_context)
        flow_type = flow.get("flow_type") or "ui"
        tests.append(
            {
                "id": f"UI_{len(tests) + 1:03d}",
                "name": f"{name}_flow_is_visible",
                "flow": name,
                "objective": f"Verify the {name} {flow_type} flow is visible at a high level.",
                "priority": "high" if name in {"login", "register", "signup"} else "medium",
                "steps": [
                    f"Open the application page associated with the discovered {name} flow.",
                    "Observe visible page content without relying on invented selectors.",
                ],
                "expected_result": f"The {name} flow is visible and usable according to discovered UI files.",
                "evidence_sources": sources,
                "risks": ["No CSS selectors are planned yet; later UI agents must discover stable locators."],
            }
        )
        if len(tests) >= 4:
            break
    return tests


def build_performance_tests(
    discovered_endpoints: list[dict[str, Any]],
    user_preferences: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Create one safe performance plan only when explicitly requested."""

    test_types = set((user_preferences or {}).get("test_types") or [])
    if "performance" not in test_types:
        return []
    for endpoint in discovered_endpoints:
        method = str(endpoint.get("method") or "UNKNOWN").upper()
        if method in {"GET", "UNKNOWN"}:
            path = normalize_endpoint_path(str(endpoint.get("path", "")))
            return [
                {
                    "id": "PERF_001",
                    "name": f"baseline_load_{path.strip('/').replace('/', '_') or 'root'}",
                    "endpoint": path,
                    "objective": f"Measure a safe baseline response time for {path}.",
                    "users": 5,
                    "duration_seconds": 30,
                    "max_avg_response_ms": 2000,
                    "evidence_sources": [endpoint.get("source_file", "")],
                    "risks": ["Safe mode only; run only against an authorized localhost or staging target."],
                }
            ]
    return []


def _scope(project_info: dict[str, Any], user_preferences: dict[str, Any] | None) -> str:
    focus = (user_preferences or {}).get("focus") or (user_preferences or {}).get("rag_query")
    if focus:
        return str(focus)
    framework = project_info.get("framework") or "Unknown framework"
    auth = project_info.get("auth_type") or "unknown auth"
    return f"{framework} testing plan with {auth} evidence"


def generate_deterministic_test_plan(
    project_info: dict[str, Any],
    discovered_endpoints: list[dict[str, Any]],
    discovered_ui_flows: list[dict[str, Any]],
    retrieved_context: list[dict[str, Any]],
    user_preferences: dict[str, Any] | None = None,
    missing_information: list[str] | None = None,
) -> dict[str, Any]:
    """Generate and validate a deterministic, evidence-grounded test plan."""

    missing = list(missing_information or [])
    api_tests = build_api_tests_from_endpoints(
        project_info,
        discovered_endpoints,
        retrieved_context,
        user_preferences,
    )
    ui_tests = build_ui_tests_from_flows(
        discovered_ui_flows,
        retrieved_context,
        user_preferences,
    )
    performance_tests = build_performance_tests(discovered_endpoints, user_preferences)

    if project_info.get("has_api") and not discovered_endpoints:
        missing.append("No discovered endpoints are available for API planning.")
    if not retrieved_context:
        missing.append("No retrieved RAG context is available to ground detailed assertions.")
    if project_info.get("has_ui") and not discovered_ui_flows:
        missing.append("No discovered UI flows are available for UI planning.")

    assumptions = []
    if str(project_info.get("auth_type", "")).upper() == "JWT":
        assumptions.append("JWT authentication evidence is used only for planning, not execution.")
    if api_tests:
        assumptions.append("Endpoint paths come from Repository Analyzer evidence.")
    if ui_tests:
        assumptions.append("UI steps stay high-level because selectors are not discovered yet.")

    plan = {
        "scope": _scope(project_info, user_preferences),
        "assumptions": assumptions,
        "api_tests": api_tests,
        "ui_tests": ui_tests,
        "performance_tests": performance_tests,
        "excluded_tests": [
            "Executable pytest, Selenium, Locust, and MCP-based tests are excluded in milestone 6."
        ],
        "missing_information": sorted(set(missing)),
        "risks": list(project_info.get("risks", [])),
        "reasoning_summary": (
            "Deterministic fallback planned tests from discovered repository endpoints, "
            "UI flows, and retrieved context without inventing executable details."
        ),
    }
    return TestPlan(**plan).model_dump(mode="json")

