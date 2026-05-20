from __future__ import annotations

from pathlib import Path

from scripts import validate_optional_llm_config
from scripts.validate_notebook_env import CORE_DEPENDENCIES
from test_auto.interface.flask_app import create_app


ROOT = Path(__file__).resolve().parents[1]


def test_readme_documents_final_mermaid_workflow() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "## Final MVP Workflow" in readme
    assert "```mermaid" in readme
    assert "PERF[Performance Testing]" in readme
    assert "START -> orchestrator -> repo_analyzer -> rag -> test_planner -> api_testing -> ui_testing -> performance_testing -> bug_analysis -> report -> END" in readme


def test_final_demo_guide_exists() -> None:
    guide = ROOT / "docs" / "final_demo_guide.md"

    assert guide.exists()
    assert "Final Workflow" in guide.read_text(encoding="utf-8")


def test_dashboard_home_shows_final_workflow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = create_app(testing=True).test_client()

    response = client.get("/")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Final MVP Workflow" in text
    assert "Performance" in text


def test_optional_llm_validation_does_not_print_secret(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    secret = "RAW_LLM_SECRET_SHOULD_NOT_APPEAR"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", secret)
    monkeypatch.setenv("GROQ_MODEL", "demo-model")

    assert validate_optional_llm_config.main() == 0
    output = capsys.readouterr().out

    assert "has_groq_key=True" in output
    assert "configured_groq_model=demo-model" in output
    assert secret not in output


def test_notebook_validation_includes_final_dependencies() -> None:
    assert "locust" in CORE_DEPENDENCIES
