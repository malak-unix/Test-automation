"""Conditional routing helpers for the main LangGraph workflow.

Routing is deliberately conservative: a node runs only when the selected agent
exists, required State inputs are present, and skip flags are not enabled. These
checks do not contact external services, run browsers, run Locust, or execute
target repository code; they only decide which LangGraph edge is safe to take.
"""

from __future__ import annotations

from pathlib import Path

from test_auto.graph.state import TestAutomationState
from test_auto.shared.utils import validate_url
from test_auto.tools.performance_tools import (
    has_unresolved_parameters,
    is_safe_performance_method,
    normalize_performance_endpoint,
)
from test_auto.tools.repo_tools import is_probably_git_url


def _local_repo_path_exists(repo_path: str | None) -> bool:
    if not repo_path:
        return False
    return Path(repo_path).expanduser().resolve().is_dir()


def has_critical_repo_input_error(state: TestAutomationState) -> bool:
    """Return True when repository input is too invalid to analyze safely."""

    repo_path = state.get("repo_path")
    repo_url = state.get("repo_url")
    if _local_repo_path_exists(repo_path):
        return False
    if repo_url and is_probably_git_url(repo_url):
        return False

    has_repo_error = any(
        error.get("field") in {"repo_url", "repo_path"}
        for error in state.get("errors", [])
    )
    return has_repo_error or not repo_url and not repo_path


def route_after_orchestrator(state: TestAutomationState) -> str:
    """Route from Orchestrator to Repository Analyzer or END."""

    selected_agents = state.get("selected_agents", [])
    if "repository_analyzer" not in selected_agents:
        return "end"
    if has_critical_repo_input_error(state):
        return "end"
    return "repo_analyzer"


def has_project_metadata_for_rag(state: TestAutomationState) -> bool:
    """Return True when Repository Analyzer produced usable RAG inputs."""

    repo_path = state.get("repo_path")
    project_info = state.get("project_info")
    indexed_documents = state.get("indexed_documents")
    if not _local_repo_path_exists(repo_path):
        return False
    if not isinstance(project_info, dict) or not project_info:
        return False
    if not isinstance(indexed_documents, list) or not indexed_documents:
        return False

    critical_repo_errors = any(
        error.get("agent") == "repo_analyzer"
        and error.get("field") in {"repo_path", "internal"}
        for error in state.get("errors", [])
    )
    return not critical_repo_errors


def route_after_repo_analyzer(state: TestAutomationState) -> str:
    """Route to RAG only when repository analysis produced usable metadata."""

    selected_agents = state.get("selected_agents", [])
    if "rag" not in selected_agents:
        return "end"
    if not has_project_metadata_for_rag(state):
        return "end"
    return "rag"


def has_planner_inputs(state: TestAutomationState) -> bool:
    """Return True when RAG produced usable inputs for Test Planner."""

    project_info = state.get("project_info")
    if not isinstance(project_info, dict) or not project_info:
        return False
    if "discovered_endpoints" not in state or not isinstance(
        state.get("discovered_endpoints"),
        list,
    ):
        return False
    if "retrieved_context" not in state or not isinstance(
        state.get("retrieved_context"),
        list,
    ):
        return False

    critical_errors = any(
        (
            error.get("agent") == "repo_analyzer"
            and error.get("field") in {"repo_url", "repo_path", "internal"}
        )
        or (
            error.get("agent") == "rag"
            and error.get("field") in {"repo_path", "internal"}
        )
        for error in state.get("errors", [])
    )
    return not critical_errors


def route_after_rag(state: TestAutomationState) -> str:
    """Route to Test Planner only when RAG produced planner evidence."""

    selected_agents = state.get("selected_agents", [])
    if "test_planner" not in selected_agents:
        return "end"
    if not has_planner_inputs(state):
        return "end"
    return "test_planner"


def has_api_testing_inputs(state: TestAutomationState) -> bool:
    """Return True when Test Planner produced executable API testing inputs."""

    test_plan = state.get("test_plan")
    if not isinstance(test_plan, dict) or not test_plan:
        return False

    api_tests = test_plan.get("api_tests")
    if not isinstance(api_tests, list) or not api_tests:
        return False

    if not validate_url(state.get("target_url", "")):
        return False

    critical_planner_errors = any(
        error.get("agent") == "test_planner"
        and error.get("field") in {"internal", "test_plan"}
        for error in state.get("errors", [])
    )
    return not critical_planner_errors


def has_ui_testing_inputs(state: TestAutomationState) -> bool:
    """Return True when Test Planner produced executable UI testing inputs."""

    test_plan = state.get("test_plan")
    if not isinstance(test_plan, dict) or not test_plan:
        return False

    ui_tests = test_plan.get("ui_tests")
    if not isinstance(ui_tests, list) or not ui_tests:
        return False

    if not validate_url(state.get("target_url", "")):
        return False

    critical_planner_errors = any(
        error.get("agent") == "test_planner"
        and error.get("field") in {"internal", "test_plan"}
        for error in state.get("errors", [])
    )
    return not critical_planner_errors


def _has_safe_performance_candidate(
    test_plan: dict,
    discovered_endpoints: list[dict] | None = None,
) -> bool:
    performance_tests = test_plan.get("performance_tests")
    if isinstance(performance_tests, list) and performance_tests:
        for item in performance_tests:
            if not isinstance(item, dict):
                continue
            method = item.get("method") or "GET"
            endpoint = normalize_performance_endpoint(item.get("endpoint") or item.get("path"))
            if is_safe_performance_method(method) and not has_unresolved_parameters(endpoint):
                return True

    api_tests = test_plan.get("api_tests")
    if isinstance(api_tests, list):
        for item in api_tests:
            if not isinstance(item, dict):
                continue
            endpoint = normalize_performance_endpoint(item.get("endpoint") or item.get("path"))
            if is_safe_performance_method(item.get("method") or "") and not has_unresolved_parameters(endpoint):
                return True

    for endpoint_info in discovered_endpoints or []:
        if not isinstance(endpoint_info, dict):
            continue
        endpoint = normalize_performance_endpoint(endpoint_info.get("path") or endpoint_info.get("endpoint"))
        method = endpoint_info.get("method") or "GET"
        if is_safe_performance_method(method) and not has_unresolved_parameters(endpoint):
            return True

    return False


def has_performance_testing_inputs(state: TestAutomationState) -> bool:
    """Return True when State has safe inputs for Performance Testing."""

    user_preferences = state.get("user_preferences") or {}
    if user_preferences.get("skip_performance_testing"):
        return False
    if not validate_url(state.get("target_url", "")):
        return False

    test_plan = state.get("test_plan")
    if not isinstance(test_plan, dict) or not test_plan:
        return False

    critical_planner_errors = any(
        error.get("agent") == "test_planner"
        and error.get("field") in {"internal", "test_plan"}
        for error in state.get("errors", [])
    )
    if critical_planner_errors:
        return False

    return _has_safe_performance_candidate(
        test_plan,
        discovered_endpoints=state.get("discovered_endpoints") or [],
    )


def _api_is_selected_and_enabled(state: TestAutomationState) -> bool:
    user_preferences = state.get("user_preferences") or {}
    if user_preferences.get("skip_api_testing"):
        return False
    return "api" in state.get("selected_agents", [])


def _ui_is_selected_and_enabled(state: TestAutomationState) -> bool:
    user_preferences = state.get("user_preferences") or {}
    if user_preferences.get("skip_ui_testing"):
        return False
    return "ui" in state.get("selected_agents", [])


def _performance_is_selected_and_enabled(state: TestAutomationState) -> bool:
    user_preferences = state.get("user_preferences") or {}
    if user_preferences.get("skip_performance_testing"):
        return False
    return "performance" in state.get("selected_agents", [])


def _bug_is_selected_and_enabled(state: TestAutomationState) -> bool:
    user_preferences = state.get("user_preferences") or {}
    if user_preferences.get("skip_bug_analysis"):
        return False
    return "bug" in state.get("selected_agents", [])


def route_after_test_planner(state: TestAutomationState) -> str:
    """Route from Test Planner to the next selected executable or summary step."""

    if _api_is_selected_and_enabled(state) and has_api_testing_inputs(state):
        return "api_testing"
    if _ui_is_selected_and_enabled(state) and has_ui_testing_inputs(state):
        return "ui_testing"
    if _performance_is_selected_and_enabled(state) and has_performance_testing_inputs(state):
        return "performance_testing"
    if _bug_is_selected_and_enabled(state) and has_bug_analysis_inputs(state):
        return "bug_analysis"
    if _report_is_selected_and_enabled(state) and has_report_inputs(state):
        return "report"
    return "end"


def has_bug_analysis_inputs(state: TestAutomationState) -> bool:
    """Return True when API, UI, or Performance Testing produced output."""

    api_results = state.get("api_results")
    if isinstance(api_results, dict) and api_results:
        return True

    api_result_path = state.get("api_result_path")
    if isinstance(api_result_path, str) and api_result_path.strip():
        return True

    ui_results = state.get("ui_results")
    if isinstance(ui_results, dict) and ui_results:
        return True

    ui_result_path = state.get("ui_result_path")
    if isinstance(ui_result_path, str) and ui_result_path.strip():
        return True

    performance_results = state.get("performance_results")
    if isinstance(performance_results, dict) and performance_results:
        return True

    performance_result_path = state.get("performance_result_path")
    return bool(
        isinstance(performance_result_path, str)
        and performance_result_path.strip()
    )


def has_report_inputs(state: TestAutomationState) -> bool:
    """Return True when State has at least one useful reportable artifact."""

    useful_fields = [
        "project_info",
        "test_plan",
        "api_results",
        "api_result_path",
        "ui_results",
        "ui_result_path",
        "screenshots",
        "performance_results",
        "performance_result_path",
        "performance_artifacts",
        "bug_results",
        "bug_result_path",
        "retrieved_context",
    ]
    for field in useful_fields:
        value = state.get(field)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, list) and value:
            return True
    return False


def _report_is_selected_and_enabled(state: TestAutomationState) -> bool:
    user_preferences = state.get("user_preferences") or {}
    if user_preferences.get("skip_report"):
        return False
    return "report" in state.get("selected_agents", [])


def route_after_api_testing(state: TestAutomationState) -> str:
    """Route API output to UI Testing, Bug Analysis, Report, or END."""

    if _ui_is_selected_and_enabled(state) and has_ui_testing_inputs(state):
        return "ui_testing"
    if _performance_is_selected_and_enabled(state) and has_performance_testing_inputs(state):
        return "performance_testing"
    if _bug_is_selected_and_enabled(state) and has_bug_analysis_inputs(state):
        return "bug_analysis"
    if _report_is_selected_and_enabled(state) and has_report_inputs(state):
        return "report"
    return "end"


def route_after_ui_testing(state: TestAutomationState) -> str:
    """Route UI output to Performance Testing, Bug Analysis, Report, or END."""

    if _performance_is_selected_and_enabled(state) and has_performance_testing_inputs(state):
        return "performance_testing"
    if _bug_is_selected_and_enabled(state):
        return "bug_analysis"
    if _report_is_selected_and_enabled(state):
        return "report"
    return "end"


def route_after_performance_testing(state: TestAutomationState) -> str:
    """Route Performance output to Bug Analysis, Report, or END."""

    if _bug_is_selected_and_enabled(state):
        return "bug_analysis"
    if _report_is_selected_and_enabled(state):
        return "report"
    return "end"


def route_after_bug_analysis(state: TestAutomationState) -> str:
    """Route Bug Analysis output to Report when reportable artifacts exist."""

    if not _report_is_selected_and_enabled(state):
        return "end"
    if not has_report_inputs(state):
        return "end"
    return "report"
