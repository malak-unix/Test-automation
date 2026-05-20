"""Optional one-call LLM planner smoke test.

By default this script does not call any LLM. Pass --use-llm to intentionally
exercise the configured Groq or Mistral planner path with a tiny fake context.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from test_auto.planning.llm_planner import generate_llm_test_plan, get_planner_llm_config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optionally smoke test LLM planning.")
    parser.add_argument("--use-llm", action="store_true")
    return parser.parse_args()


def _fake_context() -> dict:
    return {
        "project_info": {
            "language": "Python",
            "framework": "Django REST Framework",
            "has_api": True,
            "has_ui": False,
            "auth_type": "JWT",
        },
        "discovered_endpoints": [
            {
                "method": "GET",
                "path": "/api/todos/",
                "source_file": "todo/urls.py",
                "line_number": 3,
            }
        ],
        "discovered_ui_flows": [],
        "retrieved_context": [
            {
                "source_path": "README.md",
                "score": 1.0,
                "chunk_type": "doc",
                "reason": "demo context",
                "content": "JWT authentication protects the Todo API.",
            }
        ],
        "user_preferences": {"focus": "JWT todo API smoke tests"},
    }


def main() -> int:
    args = _parse_args()
    if not args.use_llm:
        print("LLM smoke test skipped. Pass --use-llm to run.")
        return 0

    config = get_planner_llm_config()
    if not config.get("available"):
        print("LLM smoke test skipped. Provider/model/key are not fully configured.")
        return 0

    try:
        plan = generate_llm_test_plan(_fake_context(), timeout_seconds=30)
    except Exception as error:
        print(f"LLM smoke test failed safely: {error.__class__.__name__}")
        return 1

    print("LLM smoke test completed.")
    print(f"scope_present={bool(plan.get('scope'))}")
    print(f"api_tests={len(plan.get('api_tests') or [])}")
    print(f"ui_tests={len(plan.get('ui_tests') or [])}")
    print(f"performance_tests={len(plan.get('performance_tests') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
