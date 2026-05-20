"""Validate that notebooks are using the project Python environment.

This script does not run the workflow, call external services, start a browser,
or require API keys. It only checks imports needed by the notebooks.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


CORE_DEPENDENCIES = [
    "langgraph",
    "pydantic",
    "flask",
    "selenium",
    "locust",
    "jupyter",
    "ipykernel",
]


def _try_import(module_name: str) -> tuple[bool, object | None, str | None]:
    try:
        module = importlib.import_module(module_name)
        return True, module, None
    except Exception as error:
        return False, None, str(error)


def _try_import_isolated(module_name: str) -> tuple[bool, str | None]:
    """Import a dependency in a fresh process.

    Locust imports gevent and monkey-patches standard libraries, so validating it
    in isolation avoids changing this diagnostic process after other libraries
    have already imported networking modules.
    """

    try:
        completed = subprocess.run(
            [sys.executable, "-c", f"import {module_name}"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception as error:
        return False, str(error)
    if completed.returncode == 0:
        return True, None
    details = (completed.stderr or completed.stdout or "import failed").strip()
    return False, details.splitlines()[0] if details else "import failed"


def main() -> int:
    """Print notebook environment diagnostics and return a validation status."""

    print("Notebook environment validation")
    print(f"Python executable: {sys.executable}")
    print(f"Current working directory: {Path.cwd()}")

    failed: list[str] = []

    ok, test_auto, error = _try_import("test_auto")
    if ok:
        print(f"test_auto import: OK")
        print(f"test_auto path: {getattr(test_auto, '__file__', 'unknown')}")
    else:
        print(f"test_auto import: FAILED ({error})")
        failed.append("test_auto")

    try:
        from test_auto.graph.workflow import run_workflow

        print(f"run_workflow import: OK ({callable(run_workflow)})")
    except Exception as error:
        print(f"run_workflow import: FAILED ({error})")
        failed.append("test_auto.graph.workflow.run_workflow")

    for dependency in CORE_DEPENDENCIES:
        if dependency == "locust":
            ok, error = _try_import_isolated(dependency)
            if ok:
                print(f"{dependency} import: OK (isolated)")
            else:
                print(f"{dependency} import: FAILED ({error})")
                failed.append(dependency)
            continue
        ok, module, error = _try_import(dependency)
        if ok:
            print(f"{dependency} import: OK")
        else:
            print(f"{dependency} import: FAILED ({error})")
            failed.append(dependency)

    if failed:
        print()
        print("Validation failed. Missing or broken imports:")
        for item in failed:
            print(f"- {item}")
        print()
        print("Fix:")
        print("  python -m pip install -r requirements.txt")
        print("  python -m pip install -e .")
        print("  python scripts/setup_notebook_kernel.py")
        return 1

    print()
    print("Notebook environment validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
