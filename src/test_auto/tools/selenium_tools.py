"""Deterministic Selenium helpers for the standalone UI Testing Agent."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from test_auto.shared.utils import ensure_directory, write_json_file
from test_auto.tools.bug_tools import mask_sensitive_values


UI_ERROR_STATUSES = {"error", "environment_error", "timeout_error", "test_data_error"}
UI_FAILED_STATUSES = {"failed", "assertion_error", "selector_error"}
MASK = "***MASKED***"
SENSITIVE_TERMS = {
    "authorization",
    "bearer",
    "cookie",
    "csrf",
    "password",
    "secret",
    "session",
    "token",
}


def normalize_path(path: str | None) -> str:
    """Normalize a page path so it starts with a slash."""

    if not path:
        return "/"
    value = str(path).strip()
    if not value:
        return "/"
    if value.startswith(("http://", "https://")):
        return value
    if value.startswith("?"):
        return f"/{value}"
    return value if value.startswith("/") else f"/{value}"


def join_page_url(base_url: str, path: str | None) -> str:
    """Join a target base URL and UI page path safely."""

    normalized = normalize_path(path)
    if normalized.startswith(("http://", "https://")):
        return normalized
    return urljoin(f"{base_url.rstrip('/')}/", normalized.lstrip("/"))


def infer_ui_path_from_flow(
    test_case: dict[str, Any],
    discovered_ui_flows: list[dict[str, Any]] | None = None,
) -> str:
    """Infer a simple page path from planned UI test metadata."""

    explicit = test_case.get("target_path") or test_case.get("path")
    if explicit:
        return normalize_path(str(explicit))

    searchable = " ".join(
        str(test_case.get(key, ""))
        for key in ("flow", "name", "objective", "expected_result")
    ).lower()
    for flow in discovered_ui_flows or []:
        searchable = f"{searchable} {flow.get('name', '')} {flow.get('flow_type', '')} {flow.get('source_file', '')}".lower()

    if "login" in searchable:
        return "/login/"
    if "register" in searchable or "signup" in searchable:
        return "/register/"
    if "dashboard" in searchable:
        return "/dashboard/"
    if any(token in searchable for token in ("todo", "todos", "task", "home", "index")):
        return "/"
    return "/"


def mask_sensitive_text(value: str | None) -> str | None:
    """Mask token-like or credential-like text before saving output."""

    if value is None:
        return None
    text = str(value)
    text = re.sub(r"bearer\s+[A-Za-z0-9._~+/=-]+", MASK, text, flags=re.IGNORECASE)
    text = re.sub(
        r"(password|token|secret|cookie|authorization|session|csrf)\s*[:=]\s*\S+",
        rf"\1={MASK}",
        text,
        flags=re.IGNORECASE,
    )
    for term in SENSITIVE_TERMS:
        text = re.sub(rf"\b{re.escape(term)}\b", MASK, text, flags=re.IGNORECASE)
    return text


def create_webdriver(headless: bool = True, browser: str = "chrome"):
    """Create a Selenium webdriver using Selenium Manager when available."""

    if browser.lower() != "chrome":
        raise RuntimeError("Only Chrome browser is supported by this UI Testing milestone.")
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1366,768")
    try:
        return webdriver.Chrome(options=options)
    except Exception as error:
        raise RuntimeError("Browser is unavailable for Selenium UI testing.") from error


def safe_quit_driver(driver) -> None:
    """Quit a Selenium driver without raising."""

    try:
        if driver is not None:
            driver.quit()
    except Exception:
        return


def _safe_filename(value: str) -> str:
    masked = mask_sensitive_text(value) or "screenshot"
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", masked).strip("._")
    return cleaned[:80] or "screenshot"


def capture_screenshot(
    driver,
    run_id: str,
    test_id: str,
    reason: str,
    results_dir: str = "results",
) -> dict[str, Any]:
    """Capture a screenshot under results/runs/<run_id>/screenshots/."""

    safe_test_id = _safe_filename(test_id)
    safe_reason = _safe_filename(reason)
    path = (
        ensure_directory(Path(results_dir) / "runs" / run_id / "screenshots")
        / f"{safe_test_id}_{safe_reason}.png"
    )
    try:
        created = bool(driver.save_screenshot(str(path)))
    except Exception:
        created = False
    return {
        "path": str(path),
        "reason": safe_reason,
        "created": created,
    }


def wait_for_page_load(driver, timeout_seconds: int = 10) -> dict[str, Any]:
    """Wait until the browser reports document.readyState complete."""

    try:
        WebDriverWait(driver, timeout_seconds).until(
            lambda item: item.execute_script("return document.readyState") == "complete"
        )
        return {"ok": True, "details": "Page loaded."}
    except TimeoutException:
        return {"ok": False, "details": "Timed out waiting for page load."}
    except WebDriverException as error:
        return {"ok": False, "details": mask_sensitive_text(str(error))}


def _body_text(driver) -> str:
    try:
        return driver.find_element(By.TAG_NAME, "body").text or ""
    except Exception:
        return ""


def page_contains_text(driver, expected_text: str) -> bool:
    """Return True when the page body contains expected text, case-insensitively."""

    if not expected_text:
        return False
    return str(expected_text).lower() in _body_text(driver).lower()


def find_login_like_form(driver) -> dict[str, bool]:
    """Detect a compact login-like form shape without saving field values."""

    try:
        inputs = driver.find_elements(By.TAG_NAME, "input")
        buttons = [
            *driver.find_elements(By.TAG_NAME, "button"),
            *driver.find_elements(By.CSS_SELECTOR, "input[type='submit']"),
        ]
    except Exception:
        return {
            "has_form": False,
            "has_username_or_email": False,
            "has_password": False,
            "has_submit": False,
        }

    has_username_or_email = False
    has_password = False
    for item in inputs:
        try:
            input_type = (item.get_attribute("type") or "").lower()
            input_name = (item.get_attribute("name") or "").lower()
            input_id = (item.get_attribute("id") or "").lower()
        except Exception:
            continue
        descriptor = f"{input_type} {input_name} {input_id}"
        if input_type == "password":
            has_password = True
        if any(token in descriptor for token in ("email", "username", "login")):
            has_username_or_email = True

    has_submit = bool(buttons)
    return {
        "has_form": bool(inputs or buttons),
        "has_username_or_email": has_username_or_email,
        "has_password": has_password,
        "has_submit": has_submit,
    }


def evaluate_ui_assertions(driver, test_case: dict[str, Any]) -> list[dict[str, Any]]:
    """Evaluate supported UI assertion types using stable page checks."""

    evaluated: list[dict[str, Any]] = []
    assertions = test_case.get("assertions") or []
    for assertion in assertions:
        assertion_type = assertion.get("type") or "unknown"
        expected = str(assertion.get("expected") or "").strip()
        target = str(assertion.get("target") or "").strip()

        if assertion_type in {"ui_visible", "page_contains"}:
            needle = expected or target
            passed = page_contains_text(driver, needle)
            evaluated.append(
                {
                    "type": assertion_type,
                    "passed": passed,
                    "details": (
                        f"Visible text found: {mask_sensitive_text(needle)}."
                        if passed
                        else f"Visible text not found: {mask_sensitive_text(needle)}."
                    ),
                }
            )
        elif assertion_type in {"form_present", "login_form_present"}:
            form = find_login_like_form(driver)
            passed = form["has_form"]
            if assertion_type == "login_form_present":
                passed = bool(
                    form["has_form"]
                    and form["has_username_or_email"]
                    and form["has_password"]
                    and form["has_submit"]
                )
            evaluated.append(
                {
                    "type": assertion_type,
                    "passed": passed,
                    "details": "Form evidence checked.",
                    "evidence": form,
                }
            )
        elif assertion_type == "title_contains":
            title = str(getattr(driver, "title", "") or "")
            passed = expected.lower() in title.lower()
            evaluated.append(
                {
                    "type": assertion_type,
                    "passed": passed,
                    "details": (
                        "Page title matched."
                        if passed
                        else f"Page title did not contain {mask_sensitive_text(expected)}."
                    ),
                }
            )
        else:
            evaluated.append(
                {
                    "type": assertion_type,
                    "passed": True,
                    "status": "skipped",
                    "details": "Unsupported UI assertion type skipped.",
                }
            )
    return evaluated


def _base_ui_result(
    target_url: str,
    test_case: dict[str, Any],
    target_path: str,
    full_url: str,
) -> dict[str, Any]:
    return {
        "id": str(test_case.get("id") or "UI_UNKNOWN"),
        "name": str(test_case.get("name") or "unnamed_ui_test"),
        "flow": test_case.get("flow"),
        "target_path": target_path,
        "target_url": full_url,
        "duration_ms": None,
        "details": None,
        "screenshot": None,
        "assertions": [],
        "error_type": None,
        "evidence": {
            "page_url": full_url,
            "title": None,
            "form": {},
        },
    }


def execute_ui_test_case(
    target_url: str,
    test_case: dict[str, Any],
    run_id: str,
    discovered_ui_flows: list[dict[str, Any]] | None = None,
    user_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one planned UI test case with Selenium and compact evidence."""

    started = time.perf_counter()
    preferences = user_preferences or {}
    target_path = infer_ui_path_from_flow(test_case, discovered_ui_flows)
    full_url = join_page_url(target_url, target_path)
    result = _base_ui_result(target_url, test_case, target_path, full_url)
    driver = None

    if not target_url:
        return {
            **result,
            "status": "test_data_error",
            "duration_ms": 0.0,
            "details": "target_url is required for UI testing.",
            "error_type": "test_data_error",
        }

    try:
        driver = create_webdriver(
            headless=bool(preferences.get("headless", True)),
            browser=str(preferences.get("browser") or "chrome"),
        )
        driver.get(full_url)
        loaded = wait_for_page_load(
            driver,
            timeout_seconds=int(preferences.get("ui_timeout_seconds") or 10),
        )
        if not loaded["ok"]:
            screenshot = capture_screenshot(driver, run_id, result["id"], "timeout_error")
            return {
                **result,
                "status": "timeout_error",
                "duration_ms": (time.perf_counter() - started) * 1000,
                "details": loaded["details"],
                "screenshot": screenshot,
                "error_type": "timeout_error",
            }

        result["evidence"]["title"] = mask_sensitive_text(str(getattr(driver, "title", "") or ""))
        result["evidence"]["form"] = find_login_like_form(driver)
        assertions = evaluate_ui_assertions(driver, test_case)
        failed_assertions = [item for item in assertions if item.get("passed") is False]
        if failed_assertions:
            screenshot = None
            if preferences.get("screenshot_on_failure", True):
                screenshot = capture_screenshot(driver, run_id, result["id"], "assertion_error")
            return {
                **result,
                "status": "assertion_error",
                "duration_ms": (time.perf_counter() - started) * 1000,
                "details": failed_assertions[0].get("details"),
                "screenshot": screenshot,
                "assertions": assertions,
                "error_type": "assertion_error",
                "evidence": result["evidence"],
            }

        return {
            **result,
            "status": "passed",
            "duration_ms": (time.perf_counter() - started) * 1000,
            "details": "UI test executed successfully.",
            "assertions": assertions,
            "evidence": result["evidence"],
        }
    except RuntimeError as error:
        return {
            **result,
            "status": "environment_error",
            "duration_ms": (time.perf_counter() - started) * 1000,
            "details": mask_sensitive_text(str(error)),
            "error_type": "environment_error",
        }
    except TimeoutException as error:
        screenshot = capture_screenshot(driver, run_id, result["id"], "timeout_error") if driver else None
        return {
            **result,
            "status": "timeout_error",
            "duration_ms": (time.perf_counter() - started) * 1000,
            "details": mask_sensitive_text(str(error)),
            "screenshot": screenshot,
            "error_type": "timeout_error",
        }
    except NoSuchElementException as error:
        screenshot = capture_screenshot(driver, run_id, result["id"], "selector_error") if driver else None
        return {
            **result,
            "status": "selector_error",
            "duration_ms": (time.perf_counter() - started) * 1000,
            "details": mask_sensitive_text(str(error)),
            "screenshot": screenshot,
            "error_type": "selector_error",
        }
    except WebDriverException as error:
        screenshot = capture_screenshot(driver, run_id, result["id"], "environment_error") if driver else None
        return {
            **result,
            "status": "environment_error",
            "duration_ms": (time.perf_counter() - started) * 1000,
            "details": mask_sensitive_text(str(error)),
            "screenshot": screenshot,
            "error_type": "environment_error",
        }
    except Exception as error:
        screenshot = capture_screenshot(driver, run_id, result["id"], "error") if driver else None
        return {
            **result,
            "status": "error",
            "duration_ms": (time.perf_counter() - started) * 1000,
            "details": mask_sensitive_text(str(error)),
            "screenshot": screenshot,
            "error_type": "error",
        }
    finally:
        safe_quit_driver(driver)


def compute_ui_summary(test_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate UI execution counts and pass rate."""

    total = len(test_results)
    passed = sum(item.get("status") == "passed" for item in test_results)
    skipped = sum(item.get("status") == "skipped" for item in test_results)
    failed = sum(item.get("status") in UI_FAILED_STATUSES for item in test_results)
    errors = sum(item.get("status") in UI_ERROR_STATUSES for item in test_results)
    return {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
    }


def save_ui_result(
    run_id: str,
    ui_output: dict[str, Any],
    results_dir: str = "results",
) -> str:
    """Save results/runs/<run_id>/ui_result.json."""

    run_dir = ensure_directory(Path(results_dir) / "runs" / run_id)
    path = write_json_file(run_dir / "ui_result.json", mask_sensitive_values(ui_output))
    return str(path)
