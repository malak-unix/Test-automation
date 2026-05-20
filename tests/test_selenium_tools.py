from __future__ import annotations

from pathlib import Path

from test_auto.tools import selenium_tools
from test_auto.tools.selenium_tools import (
    capture_screenshot,
    compute_ui_summary,
    evaluate_ui_assertions,
    infer_ui_path_from_flow,
    join_page_url,
    mask_sensitive_text,
    normalize_path,
)


class FailingScreenshotDriver:
    def save_screenshot(self, path: str) -> bool:
        raise RuntimeError("screenshot failed")


def test_join_page_url() -> None:
    assert join_page_url("http://localhost:8000", "/login/") == "http://localhost:8000/login/"


def test_normalize_path() -> None:
    assert normalize_path("login") == "/login"
    assert normalize_path("/login/") == "/login/"
    assert normalize_path(None) == "/"


def test_infer_ui_path_from_flow_login() -> None:
    path = infer_ui_path_from_flow({"name": "login_page_visible", "flow": "login"})

    assert "login" in path


def test_infer_ui_path_from_flow_register() -> None:
    path = infer_ui_path_from_flow({"name": "register_page_visible", "flow": "register"})

    assert "register" in path


def test_mask_sensitive_text() -> None:
    masked = mask_sensitive_text("password=abc token=def cookie=ghi")

    assert "abc" not in masked
    assert "def" not in masked
    assert "ghi" not in masked


def test_compute_ui_summary() -> None:
    summary = compute_ui_summary(
        [
            {"status": "passed"},
            {"status": "assertion_error"},
            {"status": "skipped"},
            {"status": "environment_error"},
        ]
    )

    assert summary["total_tests"] == 4
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
    assert summary["errors"] == 1
    assert summary["pass_rate"] == 25.0


def test_capture_screenshot_handles_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = capture_screenshot(
        FailingScreenshotDriver(),
        run_id="ui_screenshot_test",
        test_id="UI_001",
        reason="assertion_error",
    )

    assert result["created"] is False
    assert result["path"].endswith(".png")


def test_evaluate_ui_assertions_unknown_skipped() -> None:
    result = evaluate_ui_assertions(object(), {"assertions": [{"type": "custom_unknown"}]})

    assert result[0]["status"] == "skipped"
    assert result[0]["passed"] is True


def test_execute_ui_test_case_browser_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        selenium_tools,
        "create_webdriver",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("browser unavailable")),
    )

    result = selenium_tools.execute_ui_test_case(
        target_url="http://localhost:8000",
        test_case={"id": "UI_001", "name": "login", "flow": "login", "assertions": []},
        run_id="ui_browser_unavailable",
    )

    assert result["status"] == "environment_error"
