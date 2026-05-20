from __future__ import annotations

import importlib.util
from pathlib import Path

from test_auto.interface.flask_app import create_app


ROOT = Path(__file__).resolve().parents[1]
FINAL_WORKFLOW = (
    "START -> orchestrator -> repo_analyzer -> rag -> test_planner -> "
    "api_testing -> ui_testing -> performance_testing -> bug_analysis -> report -> END"
)


def test_final_workflow_imports() -> None:
    from test_auto.graph.workflow import run_workflow

    assert callable(run_workflow)


def test_dashboard_imports() -> None:
    app = create_app(testing=True)

    assert app is not None


def test_final_docs_exist() -> None:
    for relative_path in [
        "docs/demo_script.md",
        "docs/final_checklist.md",
        "docs/final_architecture.md",
        "docs/presentation_outline.md",
        "notebooks/README.md",
    ]:
        assert (ROOT / relative_path).exists()


def test_final_smoke_script_exists() -> None:
    assert (ROOT / "scripts" / "final_smoke_test.py").exists()


def test_readme_mentions_final_workflow() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert FINAL_WORKFLOW in readme
    assert "Final polishing complete" in readme


def test_github_validation_script_exists() -> None:
    assert (ROOT / "scripts" / "validate_github_input.py").exists()


def test_llm_config_validation_script_exists() -> None:
    assert (ROOT / "scripts" / "validate_llm_config.py").exists()


def test_no_obvious_secret_placeholders_committed() -> None:
    checked_files = [
        ROOT / ".env.example",
        ROOT / "README.md",
        ROOT / "docs" / "demo_script.md",
        ROOT / "docs" / "final_architecture.md",
    ]

    for path in checked_files:
        text = path.read_text(encoding="utf-8")
        assert "RAW_LLM_SECRET_SHOULD_NOT_APPEAR" not in text
        assert "SECRET_TOKEN_SHOULD_NOT_APPEAR" not in text
        assert "Bearer " not in text


def test_dashboard_css_contains_cyber_theme_classes_or_tokens() -> None:
    css = (ROOT / "static" / "dashboard.css").read_text(encoding="utf-8")

    assert "--neon" in css
    assert "--cyan" in css
    assert "agent-flow" in css
    assert "console-panel" in css


def test_performance_agent_imports() -> None:
    from test_auto.agents.performance_testing_agent import run_performance_testing_agent_alone

    assert callable(run_performance_testing_agent_alone)


def test_mcp_server_imports() -> None:
    spec = importlib.util.spec_from_file_location(
        "testing_tools_server",
        ROOT / "mcp_servers" / "testing_tools_server.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.health_check()["status"] == "ok"
