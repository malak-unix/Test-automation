"""Prompt construction helpers for future LLM-backed planning."""

from __future__ import annotations

import json
from typing import Any


TEST_PLANNER_SYSTEM_PROMPT = """
You are the Test Planner Agent for an automated software testing system.

Your task:
Create a minimal but meaningful test plan using only the evidence provided:
- project_info
- discovered_endpoints
- discovered_ui_flows
- retrieved_context
- user_preferences

Rules:
- Return strict JSON only.
- Do not wrap output in Markdown.
- Do not invent endpoints.
- Do not invent credentials.
- Do not invent selectors.
- Do not invent business rules.
- Every planned test must include evidence_sources.
- If evidence is missing, put it in missing_information.
- Do not generate executable test code.
- Do not run tests.
- Do not expose chain-of-thought.
- Include only a concise reasoning_summary.
"""


FEW_SHOT_TEST_PLAN_EXAMPLE = """
Input evidence:
project_info: Django REST Framework, JWT, has_api=true, has_ui=true
discovered_endpoints: GET/POST /api/todos/
retrieved_context: README says JWT is required for todo API.

Output:
{
  "scope": "JWT authentication and Todo CRUD",
  "assumptions": ["Authentication evidence comes from README."],
  "api_tests": [
    {
      "id": "API_001",
      "name": "unauthenticated_todo_list_is_rejected",
      "method": "GET",
      "endpoint": "/api/todos/",
      "objective": "Verify that unauthenticated users cannot list todos.",
      "priority": "high",
      "category": "security",
      "auth_required": false,
      "expected_status": 401,
      "assertions": [
        {"type": "status_code", "expected": "401"}
      ],
      "evidence_sources": ["README.md", "todo/urls.py"],
      "risks": []
    }
  ],
  "ui_tests": [],
  "performance_tests": [],
  "excluded_tests": [],
  "missing_information": [],
  "risks": [],
  "reasoning_summary": "The plan focuses on documented JWT protection for the todo API."
}
"""


def _preview(value: str, max_chars: int = 500) -> str:
    text = " ".join(value.split())
    return text[:max_chars]


def compact_context_for_prompt(
    project_info: dict[str, Any],
    discovered_endpoints: list[dict[str, Any]],
    discovered_ui_flows: list[dict[str, Any]],
    retrieved_context: list[dict[str, Any]],
    user_preferences: dict[str, Any] | None = None,
    max_context_items: int = 8,
) -> dict[str, Any]:
    """Build a compact, non-secret context payload for planner prompts."""

    compact_retrieved = []
    for item in retrieved_context[:max_context_items]:
        compact_retrieved.append(
            {
                "source_path": item.get("source_path"),
                "score": item.get("score"),
                "chunk_type": item.get("chunk_type"),
                "reason": item.get("reason"),
                "content": _preview(str(item.get("content", ""))),
            }
        )

    return {
        "project_info": project_info or {},
        "discovered_endpoints": [
            {
                "method": item.get("method") or "UNKNOWN",
                "path": item.get("path"),
                "source_file": item.get("source_file"),
                "line_number": item.get("line_number"),
            }
            for item in discovered_endpoints
        ],
        "discovered_ui_flows": [
            {
                "name": item.get("name"),
                "source_file": item.get("source_file"),
                "flow_type": item.get("flow_type"),
            }
            for item in discovered_ui_flows
        ],
        "retrieved_context": compact_retrieved,
        "user_preferences": user_preferences or {},
    }


def build_test_planner_user_prompt(context: dict[str, Any]) -> str:
    """Create the user prompt that carries compact evidence for planning."""

    return (
        "Create a strict JSON TestPlan using only this evidence. "
        "The JSON must contain scope, assumptions, api_tests, ui_tests, "
        "performance_tests, excluded_tests, missing_information, risks, and "
        "reasoning_summary.\n\n"
        f"Evidence JSON:\n{json.dumps(context, indent=2, sort_keys=True)}"
    )


def build_test_planner_messages(context: dict[str, Any]) -> list[dict[str, str]]:
    """Return system, few-shot, and user messages without calling an LLM."""

    return [
        {"role": "system", "content": TEST_PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": FEW_SHOT_TEST_PLAN_EXAMPLE},
        {"role": "user", "content": build_test_planner_user_prompt(context)},
    ]

