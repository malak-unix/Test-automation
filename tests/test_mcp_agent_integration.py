from __future__ import annotations

import json
from pathlib import Path

from test_auto.agents.api_testing_agent import run_api_testing_agent_alone
from test_auto.agents.report_agent import report_node, run_report_agent_alone
from test_auto.agents.repo_analyzer import analyze_repository
from test_auto.graph.workflow import run_workflow
from test_auto.interface.run_service import build_initial_state_from_form
from test_auto.shared.utils import json_safe


def write_file(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_fake_django_rest_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_django_rest_repo"
    write_file(repo, "README.md", "# Fake Django REST API")
    write_file(repo, "requirements.txt", "django\ndjangorestframework\npytest\n")
    write_file(repo, "manage.py", "# django manage placeholder\n")
    write_file(
        repo,
        "todo/urls.py",
        "from django.urls import path\nfrom . import views\nurlpatterns = [path('api/todos/', views.todos)]\n",
    )
    write_file(
        repo,
        "todo/views.py",
        "from rest_framework.decorators import api_view\n@api_view(['GET'])\ndef todos(request): pass\n",
    )
    write_file(repo, "templates/login.html", "<form>login</form>")
    write_file(repo, "tests/test_todo_api.py", "def test_todo_api(): assert True\n")
    return repo


def fake_test_plan() -> dict:
    return {
        "api_tests": [
            {
                "id": "API_001",
                "name": "List todos",
                "method": "GET",
                "endpoint": "/api/todos/",
                "expected_status": 200,
                "assertions": [],
            }
        ]
    }


def fake_report_context(run_id: str = "mcp_report_test") -> dict:
    return {
        "run_id": run_id,
        "target_url": "http://localhost:8000",
        "project_info": {"language": "Python", "framework": "Django REST Framework"},
        "test_plan": fake_test_plan(),
        "api_results": {
            "summary": {
                "total_tests": 1,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "errors": 0,
                "pass_rate": 100.0,
            },
            "tests": [{"id": "API_001", "name": "List todos", "status": "passed"}],
        },
        "bug_results": {
            "summary": {
                "total_anomalies": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "info": 0,
            },
            "anomalies": [],
            "recommendations": [],
        },
        "errors": [],
        "agent_logs": [],
    }


def test_repo_analyzer_uses_local_by_default(tmp_path: Path) -> None:
    repo = make_fake_django_rest_repo(tmp_path)

    result = analyze_repository(repo_path=str(repo))

    assert result["agent_output"]["metadata"]["tool_backend"] == "local"
    assert result["agent_output"]["metadata"]["mcp_fallback_used"] is False


def test_repo_analyzer_records_mcp_backend_when_mocked_success(tmp_path: Path, monkeypatch) -> None:
    repo = make_fake_django_rest_repo(tmp_path)

    def fake_invoke(tool_name, args, **kwargs):
        assert tool_name == "list_project_files_tool"
        return {
            "status": "success",
            "tool_name": tool_name,
            "result": {
                "status": "success",
                "files": [
                    "README.md",
                    "requirements.txt",
                    "manage.py",
                    "todo/urls.py",
                    "todo/views.py",
                    "templates/login.html",
                    "tests/test_todo_api.py",
                ],
            },
            "error": None,
        }

    monkeypatch.setattr("test_auto.mcp.tool_router.invoke_mcp_tool_sync", fake_invoke)
    result = analyze_repository(
        repo_path=str(repo),
        user_preferences={"use_mcp_tools": True},
    )

    assert result["agent_output"]["metadata"]["tool_backend"] == "mcp"
    assert result["agent_output"]["metadata"]["mcp_fallback_used"] is False


def test_repo_analyzer_falls_back_to_local_if_mcp_fails(tmp_path: Path, monkeypatch) -> None:
    repo = make_fake_django_rest_repo(tmp_path)
    monkeypatch.setattr(
        "test_auto.mcp.tool_router.invoke_mcp_tool_sync",
        lambda *args, **kwargs: {
            "status": "error",
            "tool_name": "list_project_files_tool",
            "result": None,
            "error": "offline",
        },
    )

    result = analyze_repository(
        repo_path=str(repo),
        user_preferences={"use_mcp_tools": True},
    )

    assert result["agent_output"]["metadata"]["tool_backend"] == "mixed"
    assert result["agent_output"]["metadata"]["mcp_fallback_used"] is True


def test_api_testing_uses_local_by_default() -> None:
    result = run_api_testing_agent_alone(
        target_url="http://127.0.0.1:9",
        test_plan=fake_test_plan(),
        run_id="api_local_default",
        allow_mutating=False,
    )

    assert result["agent_output"]["metadata"]["tool_backend"] == "local"


def test_api_testing_can_use_mcp_send_http_request_tool(monkeypatch) -> None:
    monkeypatch.setattr(
        "test_auto.mcp.tool_router.invoke_mcp_tool_sync",
        lambda *args, **kwargs: {
            "status": "success",
            "tool_name": "send_http_request_tool",
            "result": {
                "status": "success",
                "status_code": 200,
                "duration_ms": 12.0,
                "text_preview": "[]",
                "json_preview": [],
                "error": None,
                "error_type": None,
            },
            "error": None,
        },
    )

    result = run_api_testing_agent_alone(
        target_url="http://localhost:8000",
        test_plan=fake_test_plan(),
        run_id="api_mcp_success",
        user_preferences={"use_mcp_tools": True},
        allow_mutating=False,
    )

    assert result["agent_output"]["metadata"]["tool_backend"] == "mcp"
    assert result["summary"]["passed"] == 1


def test_api_testing_falls_back_to_local_when_mcp_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "test_auto.mcp.tool_router.invoke_mcp_tool_sync",
        lambda *args, **kwargs: {
            "status": "error",
            "tool_name": "send_http_request_tool",
            "result": None,
            "error": "offline",
        },
    )

    result = run_api_testing_agent_alone(
        target_url="http://127.0.0.1:9",
        test_plan=fake_test_plan(),
        run_id="api_mcp_fallback",
        user_preferences={"use_mcp_tools": True, "api_timeout_seconds": 1},
        allow_mutating=False,
    )

    assert result["agent_output"]["metadata"]["tool_backend"] == "mixed"
    assert result["agent_output"]["metadata"]["mcp_fallback_used"] is True


def test_report_agent_uses_local_by_default() -> None:
    result = run_report_agent_alone(context=fake_report_context("report_local_default"))

    assert result["report_result"]["metadata"]["tool_backend"] == "local"


def test_report_agent_can_use_mcp_report_tool(monkeypatch) -> None:
    def fake_invoke(tool_name, args, **kwargs):
        output_path = Path(args["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("<html>MCP report</html>", encoding="utf-8")
        return {
            "status": "success",
            "tool_name": tool_name,
            "result": {
                "status": "success",
                "report_html_path": str(output_path),
                "error": None,
            },
            "error": None,
        }

    monkeypatch.setattr("test_auto.mcp.tool_router.invoke_mcp_tool_sync", fake_invoke)
    context = fake_report_context("report_mcp_success")
    context["user_preferences"] = {"use_mcp_tools": True}

    result = run_report_agent_alone(context=context)

    assert result["report_result"]["metadata"]["tool_backend"] == "mcp"
    assert Path(result["report_html_path"]).exists()


def test_report_agent_falls_back_to_local_when_mcp_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "test_auto.mcp.tool_router.invoke_mcp_tool_sync",
        lambda *args, **kwargs: {
            "status": "error",
            "tool_name": "generate_html_report_tool",
            "result": None,
            "error": "offline",
        },
    )
    context = fake_report_context("report_mcp_fallback")
    context["user_preferences"] = {"use_mcp_tools": True}

    result = run_report_agent_alone(context=context)

    assert result["report_result"]["metadata"]["tool_backend"] == "mixed"
    assert result["report_result"]["metadata"]["mcp_fallback_used"] is True


def test_full_main_workflow_completes_with_use_mcp_tools_true_and_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = make_fake_django_rest_repo(tmp_path)
    monkeypatch.setattr(
        "test_auto.mcp.tool_router.invoke_mcp_tool_sync",
        lambda *args, **kwargs: {
            "status": "error",
            "tool_name": args[0] if args else "tool",
            "result": None,
            "error": "offline",
        },
    )

    final_state = run_workflow(
        {
            "repo_path": str(repo),
            "target_url": "http://127.0.0.1:9",
            "user_preferences": {
                "test_types": ["api"],
                "execution_mode": "sequential",
                "focus": "JWT authentication todo CRUD API tests",
                "rag_top_k": 4,
                "planner_use_llm": False,
                "allow_mutating_api_tests": False,
                "use_mcp_tools": True,
                "api_timeout_seconds": 1,
            },
            "errors": [],
            "agent_logs": [],
        }
    )

    assert final_state.get("api_result_path")
    assert final_state.get("bug_result_path")
    assert final_state.get("report_html_path")
    assert any(
        (log.get("metadata") or {}).get("mcp_fallback_used")
        for log in final_state.get("agent_logs", [])
        if isinstance(log, dict)
    )


def test_dashboard_form_parses_use_mcp_tools_checkbox() -> None:
    state = build_initial_state_from_form(
        {
            "target_url": "http://localhost:8000",
            "use_mcp_tools": "on",
        }
    )

    assert state["user_preferences"]["use_mcp_tools"] is True


def test_no_token_appears_in_report_state_or_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        "test_auto.mcp.tool_router.invoke_mcp_tool_sync",
        lambda *args, **kwargs: {
            "status": "error",
            "tool_name": "generate_html_report_tool",
            "result": None,
            "error": "Bearer SECRET_TOKEN_SHOULD_NOT_APPEAR",
        },
    )
    state = fake_report_context("report_token_masking")
    state["user_preferences"] = {
        "use_mcp_tools": True,
        "auth_token": "SECRET_TOKEN_SHOULD_NOT_APPEAR",
    }

    patch = report_node(state)

    assert "SECRET_TOKEN_SHOULD_NOT_APPEAR" not in json.dumps(json_safe(patch))
