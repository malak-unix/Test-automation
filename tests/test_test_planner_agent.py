from __future__ import annotations

import json
from pathlib import Path

from test_auto.planning import llm_planner
from test_auto.agents.test_planner import (
    load_planner_context_from_run_dir,
    run_test_planner_alone,
    test_planner_node as planner_node,
)


def fake_project_info() -> dict:
    return {
        "language": "Python",
        "framework": "Django REST Framework",
        "has_api": True,
        "has_ui": True,
        "auth_type": "JWT",
    }


def fake_endpoints() -> list[dict]:
    return [
        {
            "method": "UNKNOWN",
            "path": "/api/todos/",
            "source_file": "todo/urls.py",
        }
    ]


def fake_ui_flows() -> list[dict]:
    return [
        {
            "name": "login",
            "source_file": "templates/login.html",
            "flow_type": "authentication",
        }
    ]


def fake_context() -> list[dict]:
    return [
        {
            "source_path": "README.md",
            "content": "JWT authentication is required for Todo CRUD API operations.",
            "score": 0.9,
            "reason": "JWT and CRUD evidence",
            "chunk_type": "doc",
        }
    ]


def test_run_test_planner_alone_deterministic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_test_planner_alone(
        project_info=fake_project_info(),
        discovered_endpoints=fake_endpoints(),
        discovered_ui_flows=fake_ui_flows(),
        retrieved_context=fake_context(),
        user_preferences={"test_types": ["api", "ui"]},
        use_llm=False,
    )

    assert result["run_id"]
    assert result["test_plan"]
    assert Path(result["test_plan_path"]).exists()
    assert Path(result["test_planner_result_path"]).exists()
    assert result["planner_model_info"]["mode"] == "deterministic_fallback"


def test_test_planner_node_returns_state_patch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    update = planner_node(
        {
            "run_id": "planner_node_test",
            "project_info": fake_project_info(),
            "discovered_endpoints": fake_endpoints(),
            "discovered_ui_flows": fake_ui_flows(),
            "retrieved_context": fake_context(),
            "user_preferences": {"test_types": ["api"], "use_llm": False},
            "missing_information": [],
            "errors": [],
            "agent_logs": [],
        }
    )

    assert update["test_plan"]
    assert update["test_plan_path"]
    assert update["test_planner_result_path"]
    assert update["planner_model_info"]
    assert update["agent_logs"]


def test_test_planner_handles_missing_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_test_planner_alone(project_info={}, use_llm=False)

    assert result["test_plan"]["missing_information"]
    assert Path(result["test_plan_path"]).exists()


def test_cli_run_dir_loading(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = Path("results") / "runs" / "run_for_planner"
    run_dir.mkdir(parents=True)
    (run_dir / "project_info.json").write_text(
        json.dumps(fake_project_info()),
        encoding="utf-8",
    )
    (run_dir / "repo_analyzer_result.json").write_text(
        json.dumps(
            {
                "discovered_endpoints": fake_endpoints(),
                "discovered_ui_flows": fake_ui_flows(),
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "retrieved_context.json").write_text(
        json.dumps(fake_context()),
        encoding="utf-8",
    )

    context = load_planner_context_from_run_dir(run_dir)
    result = run_test_planner_alone(**context, run_id=run_dir.name, use_llm=False)

    assert context["discovered_endpoints"]
    assert result["test_plan"]["api_tests"]


def test_no_secret_exposure_in_model_info(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "placeholder")
    monkeypatch.setenv("GROQ_MODEL", "fake-model")

    result = run_test_planner_alone(
        project_info=fake_project_info(),
        discovered_endpoints=fake_endpoints(),
        retrieved_context=fake_context(),
        use_llm=False,
    )

    assert "placeholder" not in json.dumps(result["planner_model_info"])


def test_llm_planner_imports_and_falls_back_without_api_key(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_MODEL", "fake-model")

    context = {
        "project_info": fake_project_info(),
        "discovered_endpoints": fake_endpoints(),
        "discovered_ui_flows": fake_ui_flows(),
        "retrieved_context": fake_context(),
        "user_preferences": {"test_types": ["api"]},
        "missing_information": [],
    }
    test_plan, model_info = llm_planner.plan_with_llm_or_fallback(
        context,
        context,
    )

    assert test_plan["api_tests"]
    assert model_info["mode"] == "deterministic_fallback"
    assert model_info["provider"] == "none"
    assert model_info["model"] is None
    assert "reason" in model_info
