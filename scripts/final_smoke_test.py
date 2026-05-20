"""Final MVP smoke test for presentation readiness.

This script does not require internet, a browser, Locust execution, target app
availability, or LLM API calls.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC, ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


CHECKS = [
    "import test_auto",
    "import run_workflow",
    "import Flask create_app",
    "import MCP health_check",
    "import performance agent",
    "notebooks directory exists",
    "config example exists",
    "dashboard templates exist",
    "report template exists",
    "README mentions final workflow",
    "GitHub validation helper imports",
    "LLM config helper imports",
]


def _record(label: str, ok: bool, failures: list[str], detail: str = "") -> None:
    status = "OK" if ok else "FAILED"
    suffix = f" - {detail}" if detail else ""
    print(f"{status}: {label}{suffix}")
    if not ok:
        failures.append(label)


def main() -> int:
    failures: list[str] = []
    print("Final MVP smoke test")
    print(f"Project root: {ROOT}")

    try:
        import test_auto  # noqa: F401

        _record(CHECKS[0], True, failures)
    except Exception as error:
        _record(CHECKS[0], False, failures, error.__class__.__name__)

    try:
        from test_auto.graph.workflow import run_workflow

        _record(CHECKS[1], callable(run_workflow), failures)
    except Exception as error:
        _record(CHECKS[1], False, failures, error.__class__.__name__)

    try:
        from test_auto.interface.flask_app import create_app

        _record(CHECKS[2], callable(create_app), failures)
    except Exception as error:
        _record(CHECKS[2], False, failures, error.__class__.__name__)

    try:
        from mcp_servers.testing_tools_server import health_check

        _record(CHECKS[3], health_check().get("status") == "ok", failures)
    except Exception as error:
        _record(CHECKS[3], False, failures, error.__class__.__name__)

    try:
        from test_auto.agents import performance_testing_agent

        _record(
            CHECKS[4],
            hasattr(performance_testing_agent, "performance_testing_node"),
            failures,
        )
    except Exception as error:
        _record(CHECKS[4], False, failures, error.__class__.__name__)

    _record(CHECKS[5], (ROOT / "notebooks").is_dir(), failures)
    _record(CHECKS[6], (ROOT / "config" / "config.example.yml").is_file(), failures)
    _record(
        CHECKS[7],
        all((ROOT / "templates" / name).is_file() for name in ("base.html", "index.html", "run_result.html")),
        failures,
    )
    _record(CHECKS[8], (ROOT / "reports" / "templates" / "report.html.j2").is_file(), failures)

    readme = (ROOT / "README.md").read_text(encoding="utf-8", errors="ignore")
    _record(
        CHECKS[9],
        "START -> orchestrator -> repo_analyzer -> rag -> test_planner -> api_testing -> ui_testing -> performance_testing -> bug_analysis -> report -> END" in readme,
        failures,
    )

    try:
        import validate_github_input  # noqa: F401

        _record(CHECKS[10], True, failures)
    except Exception as error:
        _record(CHECKS[10], False, failures, error.__class__.__name__)

    try:
        import validate_llm_config  # noqa: F401

        _record(CHECKS[11], True, failures)
    except Exception as error:
        _record(CHECKS[11], False, failures, error.__class__.__name__)

    if failures:
        print()
        print("Final smoke test failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print()
    print("Final smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
