"""Safe local tools for standalone performance testing with Locust."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from test_auto.shared.utils import ensure_directory, json_safe, write_json_file
from test_auto.tools.bug_tools import mask_sensitive_values


DEFAULT_USERS = 5
DEFAULT_SPAWN_RATE = 1.0
DEFAULT_DURATION_SECONDS = 15
DEFAULT_MAX_USERS = 20
DEFAULT_MAX_DURATION_SECONDS = 60
DEFAULT_MAX_AVG_RESPONSE_MS = 2000.0
DEFAULT_MAX_P95_RESPONSE_MS = 5000.0
DEFAULT_MAX_FAILURE_RATE = 5.0
DEFAULT_MAX_PERFORMANCE_TESTS = 2
LOCUST_PREVIEW_CHARS = 500
SAFE_METHODS = {"GET", "HEAD"}


def is_local_target(target_url: str) -> bool:
    """Return True for localhost-style targets that are safe by default."""

    try:
        parsed = urlparse(target_url or "")
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = (parsed.hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def normalize_performance_endpoint(endpoint: str | None) -> str:
    """Normalize a performance endpoint path without expanding dynamic params."""

    if not endpoint:
        return "/"
    value = str(endpoint).strip()
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        value = parsed.path or "/"
        if parsed.query:
            value = f"{value}?{parsed.query}"
    if not value.startswith("/"):
        value = f"/{value}"
    return value or "/"


def has_unresolved_parameters(endpoint: str | None) -> bool:
    """Return True when an endpoint contains dynamic route placeholders."""

    path = normalize_performance_endpoint(endpoint)
    if any(marker in path for marker in ("{", "}", "<", ">")):
        return True
    return any(segment.startswith(":") for segment in path.split("/"))


def is_safe_performance_method(method: str) -> bool:
    """Return True only for safe read-only performance test methods."""

    return str(method or "").upper() in SAFE_METHODS


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp_load_settings(
    users: int,
    spawn_rate: float,
    duration_seconds: int,
    user_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Clamp requested load settings to safe local-demo defaults."""

    preferences = user_preferences or {}
    max_users = _safe_int(preferences.get("max_performance_users"), DEFAULT_MAX_USERS)
    max_duration = _safe_int(
        preferences.get("max_performance_duration_seconds"),
        DEFAULT_MAX_DURATION_SECONDS,
    )
    max_users = max(1, min(max_users, DEFAULT_MAX_USERS))
    max_duration = max(1, min(max_duration, DEFAULT_MAX_DURATION_SECONDS))

    requested_users = _safe_int(
        preferences.get("performance_users", users),
        DEFAULT_USERS,
    )
    requested_spawn_rate = _safe_float(
        preferences.get("performance_spawn_rate", spawn_rate),
        DEFAULT_SPAWN_RATE,
    )
    requested_duration = _safe_int(
        preferences.get("performance_duration_seconds", duration_seconds),
        DEFAULT_DURATION_SECONDS,
    )

    warnings: list[str] = []
    clamped_users = max(1, min(requested_users, max_users))
    clamped_spawn_rate = max(0.1, requested_spawn_rate)
    clamped_duration = max(1, min(requested_duration, max_duration))
    if clamped_users != requested_users:
        warnings.append(f"users clamped to {clamped_users}")
    if clamped_duration != requested_duration:
        warnings.append(f"duration_seconds clamped to {clamped_duration}")

    return {
        "users": clamped_users,
        "spawn_rate": clamped_spawn_rate,
        "duration_seconds": clamped_duration,
        "warnings": warnings,
    }


def _normalize_test_case(raw_case: dict[str, Any], index: int = 1) -> dict[str, Any]:
    method = str(raw_case.get("method") or "GET").upper()
    endpoint = normalize_performance_endpoint(
        raw_case.get("endpoint") or raw_case.get("path") or "/"
    )
    return {
        "id": str(raw_case.get("id") or f"PERF_{index:03d}"),
        "name": str(raw_case.get("name") or f"performance_{endpoint.strip('/') or 'home'}"),
        "endpoint": endpoint,
        "method": method,
        "objective": str(raw_case.get("objective") or "Measure basic response performance."),
        "users": _safe_int(raw_case.get("users"), DEFAULT_USERS),
        "spawn_rate": _safe_float(raw_case.get("spawn_rate"), DEFAULT_SPAWN_RATE),
        "duration_seconds": _safe_int(
            raw_case.get("duration_seconds"),
            DEFAULT_DURATION_SECONDS,
        ),
        "max_avg_response_ms": _safe_float(
            raw_case.get("max_avg_response_ms"),
            DEFAULT_MAX_AVG_RESPONSE_MS,
        ),
        "max_p95_response_ms": _safe_float(
            raw_case.get("max_p95_response_ms"),
            DEFAULT_MAX_P95_RESPONSE_MS,
        ),
        "max_failure_rate": _safe_float(
            raw_case.get("max_failure_rate")
            if raw_case.get("max_failure_rate") is not None
            else raw_case.get("max_failure_rate_percent"),
            DEFAULT_MAX_FAILURE_RATE,
        ),
    }


def build_performance_tests_from_plan(
    test_plan: dict[str, Any],
    discovered_endpoints: list[dict[str, Any]] | None = None,
    user_preferences: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build safe performance tests from planned tests or inferred GET endpoints."""

    preferences = user_preferences or {}
    max_tests = max(
        1,
        min(
            _safe_int(preferences.get("max_performance_tests"), DEFAULT_MAX_PERFORMANCE_TESTS),
            DEFAULT_MAX_PERFORMANCE_TESTS,
        ),
    )

    candidates: list[dict[str, Any]] = []
    for raw_case in (test_plan or {}).get("performance_tests") or []:
        if isinstance(raw_case, dict):
            candidates.append(raw_case)

    if not candidates:
        for api_case in (test_plan or {}).get("api_tests") or []:
            if not isinstance(api_case, dict):
                continue
            if is_safe_performance_method(api_case.get("method", "")):
                candidates.append(
                    {
                        "id": f"PERF_FROM_{api_case.get('id', 'API')}",
                        "name": f"performance_{api_case.get('name', 'api_get')}",
                        "endpoint": api_case.get("endpoint") or "/",
                        "method": api_case.get("method") or "GET",
                        "objective": "Small safe performance check inferred from API plan.",
                    }
                )
                break

    if not candidates:
        for endpoint in discovered_endpoints or []:
            if not isinstance(endpoint, dict):
                continue
            method = endpoint.get("method") or "GET"
            if is_safe_performance_method(method):
                candidates.append(
                    {
                        "id": "PERF_DISCOVERED_001",
                        "name": "performance_discovered_endpoint",
                        "endpoint": endpoint.get("path") or "/",
                        "method": method,
                        "objective": "Small safe performance check inferred from repository endpoints.",
                    }
                )
                break

    if not candidates:
        candidates.append(
            {
                "id": "PERF_001",
                "name": "performance_home",
                "endpoint": "/",
                "method": "GET",
                "objective": "Small safe performance check for the target home page.",
            }
        )

    normalized: list[dict[str, Any]] = []
    for index, raw_case in enumerate(candidates, start=1):
        test_case = _normalize_test_case(raw_case, index=index)
        if not is_safe_performance_method(test_case["method"]):
            continue
        if has_unresolved_parameters(test_case["endpoint"]):
            continue
        normalized.append(test_case)
        if len(normalized) >= max_tests:
            break
    return normalized


def create_locustfile_content(test_case: dict[str, Any]) -> str:
    """Generate a minimal Locust file for one safe endpoint."""

    endpoint = normalize_performance_endpoint(test_case.get("endpoint"))
    method = str(test_case.get("method") or "GET").upper()
    if method not in SAFE_METHODS:
        method = "GET"
    task_call = "self.client.head" if method == "HEAD" else "self.client.get"
    endpoint_literal = json.dumps(endpoint)
    return (
        '"""Generated safe Locust file for SMA Test Automation."""\n\n'
        "from locust import HttpUser, between, task\n\n\n"
        "class SafePerformanceUser(HttpUser):\n"
        "    wait_time = between(1, 2)\n\n"
        "    @task\n"
        "    def run_endpoint(self):\n"
        f"        {task_call}({endpoint_literal}, name={endpoint_literal})\n"
    )


def _safe_test_id(test_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(test_id or "performance_test"))
    return safe.strip("._") or "performance_test"


def save_locustfile(
    run_id: str,
    test_case: dict[str, Any],
    results_dir: str = "results",
) -> str:
    """Save a generated Locust file under results/runs/<run_id>/performance/."""

    performance_dir = ensure_directory(Path(results_dir) / "runs" / run_id / "performance")
    test_id = _safe_test_id(test_case.get("id", "PERF_001"))
    locustfile_path = performance_dir / f"locustfile_{test_id}.py"
    locustfile_path.write_text(create_locustfile_content(test_case), encoding="utf-8")
    return str(locustfile_path)


def _preview(text: str | None, limit: int = LOCUST_PREVIEW_CHARS) -> str:
    safe_text = mask_sensitive_values(text or "")
    return str(safe_text)[:limit]


def run_locust_subprocess(
    locustfile_path: str,
    target_url: str,
    users: int,
    spawn_rate: float,
    duration_seconds: int,
    run_id: str,
    test_id: str,
    results_dir: str = "results",
) -> dict[str, Any]:
    """Run Locust headlessly and save CSV metrics under the run performance folder."""

    performance_dir = ensure_directory(Path(results_dir) / "runs" / run_id / "performance")
    csv_prefix = performance_dir / _safe_test_id(test_id)
    command = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        str(locustfile_path),
        "--headless",
        "-u",
        str(users),
        "-r",
        str(spawn_rate),
        "-t",
        f"{duration_seconds}s",
        "--host",
        target_url,
        "--csv",
        str(csv_prefix),
        "--only-summary",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(duration_seconds + 15, 20),
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "status": "error",
            "error_type": "configuration_error",
            "csv_prefix": str(csv_prefix),
            "stdout_preview": "",
            "stderr_preview": "",
            "returncode": None,
            "error": "Locust executable is not available.",
            "details": str(exc),
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error_type": "environment_error",
            "csv_prefix": str(csv_prefix),
            "stdout_preview": "",
            "stderr_preview": "",
            "returncode": None,
            "error": "Locust run timed out before completing.",
        }

    stderr_preview = _preview(completed.stderr)
    stdout_preview = _preview(completed.stdout)
    if completed.returncode != 0:
        lowered = f"{stdout_preview}\n{stderr_preview}".lower()
        error_type = "configuration_error" if "no module named locust" in lowered else "environment_error"
        if Path(f"{csv_prefix}_stats.csv").exists():
            return {
                "status": "success",
                "error_type": None,
                "csv_prefix": str(csv_prefix),
                "stdout_preview": stdout_preview,
                "stderr_preview": stderr_preview,
                "returncode": completed.returncode,
                "error": "Locust completed with HTTP failures captured in CSV metrics.",
            }
        return {
            "status": "error",
            "error_type": error_type,
            "csv_prefix": str(csv_prefix),
            "stdout_preview": stdout_preview,
            "stderr_preview": stderr_preview,
            "returncode": completed.returncode,
            "error": "Locust run failed.",
        }

    return {
        "status": "success",
        "error_type": None,
        "csv_prefix": str(csv_prefix),
        "stdout_preview": stdout_preview,
        "stderr_preview": stderr_preview,
        "returncode": completed.returncode,
        "error": None,
    }


def _first_present(row: dict[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in row and row[name] not in {"", None}:
            return row[name]
    return None


def parse_locust_csv(csv_prefix: str) -> dict[str, Any]:
    """Parse Locust stats CSV output into compact performance metrics."""

    stats_path = Path(f"{csv_prefix}_stats.csv")
    if not stats_path.exists():
        return {"metrics": {}, "error": "Locust stats CSV was not created."}

    try:
        with stats_path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
    except OSError as exc:
        return {"metrics": {}, "error": f"Could not read Locust stats CSV: {exc}"}

    if not rows:
        return {"metrics": {}, "error": "Locust stats CSV is empty."}

    selected = next((row for row in rows if row.get("Name") == "Aggregated"), rows[0])
    total_requests = _safe_int(
        _first_present(selected, ("Request Count", "Requests", "# requests")),
        0,
    )
    failures = _safe_int(
        _first_present(selected, ("Failure Count", "Failures", "# failures")),
        0,
    )
    failure_rate = (failures / total_requests * 100.0) if total_requests else 0.0
    metrics = {
        "total_requests": total_requests,
        "failures": failures,
        "failure_rate": round(failure_rate, 2),
        "average_response_time_ms": _safe_float(
            _first_present(selected, ("Average Response Time", "Avg")),
            0.0,
        ),
        "min_response_time_ms": _safe_float(
            _first_present(selected, ("Min Response Time", "Min")),
            0.0,
        ),
        "max_response_time_ms": _safe_float(
            _first_present(selected, ("Max Response Time", "Max")),
            0.0,
        ),
        "p50_response_time_ms": _safe_float(
            _first_present(selected, ("50%", "Median Response Time", "Median")),
            0.0,
        ),
        "p95_response_time_ms": _safe_float(
            _first_present(selected, ("95%",)),
            0.0,
        ),
        "requests_per_second": _safe_float(
            _first_present(selected, ("Requests/s", "Reqs/s")),
            0.0,
        ),
    }
    return {"metrics": metrics, "error": None}


def evaluate_performance_thresholds(
    metrics: dict[str, Any],
    test_case: dict[str, Any],
    user_preferences: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate performance metrics against conservative default thresholds."""

    preferences = user_preferences or {}
    max_avg = _safe_float(
        test_case.get("max_avg_response_ms")
        if test_case.get("max_avg_response_ms") is not None
        else preferences.get("max_avg_response_ms"),
        DEFAULT_MAX_AVG_RESPONSE_MS,
    )
    max_p95 = _safe_float(
        test_case.get("max_p95_response_ms")
        if test_case.get("max_p95_response_ms") is not None
        else preferences.get("max_p95_response_ms"),
        DEFAULT_MAX_P95_RESPONSE_MS,
    )
    max_failure_rate = _safe_float(
        test_case.get("max_failure_rate")
        if test_case.get("max_failure_rate") is not None
        else preferences.get("max_failure_rate_percent"),
        DEFAULT_MAX_FAILURE_RATE,
    )
    avg = _safe_float(metrics.get("average_response_time_ms"), 0.0)
    p95 = _safe_float(metrics.get("p95_response_time_ms"), 0.0)
    failure_rate = _safe_float(metrics.get("failure_rate"), 0.0)
    return [
        {
            "name": "average_response_time",
            "passed": avg <= max_avg,
            "actual": avg,
            "threshold": max_avg,
            "unit": "ms",
        },
        {
            "name": "p95_response_time",
            "passed": p95 <= max_p95,
            "actual": p95,
            "threshold": max_p95,
            "unit": "ms",
        },
        {
            "name": "failure_rate",
            "passed": failure_rate <= max_failure_rate,
            "actual": failure_rate,
            "threshold": max_failure_rate,
            "unit": "percent",
        },
    ]


def _base_result(
    test_case: dict[str, Any],
    settings: dict[str, Any],
    status: str,
    details: str,
    error_type: str | None = None,
    artifact_paths: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(test_case.get("id") or "PERF_UNKNOWN"),
        "name": str(test_case.get("name") or "performance_test"),
        "endpoint": normalize_performance_endpoint(test_case.get("endpoint")),
        "method": str(test_case.get("method") or "GET").upper()
        if is_safe_performance_method(test_case.get("method", "GET"))
        else "GET",
        "status": status,
        "users": int(settings.get("users", DEFAULT_USERS)),
        "spawn_rate": float(settings.get("spawn_rate", DEFAULT_SPAWN_RATE)),
        "duration_seconds": int(settings.get("duration_seconds", DEFAULT_DURATION_SECONDS)),
        "total_requests": 0,
        "failures": 0,
        "failure_rate": 0.0,
        "average_response_time_ms": None,
        "min_response_time_ms": None,
        "max_response_time_ms": None,
        "p50_response_time_ms": None,
        "p95_response_time_ms": None,
        "requests_per_second": None,
        "threshold_results": [],
        "details": details,
        "error_type": error_type,
        "artifact_paths": artifact_paths or [],
    }


def execute_performance_test_case(
    target_url: str,
    test_case: dict[str, Any],
    run_id: str,
    user_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one safe performance test case using a generated Locust file."""

    preferences = user_preferences or {}
    normalized = _normalize_test_case(test_case)
    settings = clamp_load_settings(
        users=normalized["users"],
        spawn_rate=normalized["spawn_rate"],
        duration_seconds=normalized["duration_seconds"],
        user_preferences=preferences,
    )
    allow_external = bool(preferences.get("allow_external_performance_test", False))
    parsed = urlparse(target_url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return _base_result(
            normalized,
            settings,
            status="environment_error",
            details="target_url must be a valid HTTP or HTTPS URL.",
            error_type="environment_error",
        )
    if not is_local_target(target_url) and not allow_external:
        return _base_result(
            normalized,
            settings,
            status="skipped",
            details="External performance targets are disabled by default.",
            error_type=None,
        )
    if not is_safe_performance_method(normalized["method"]):
        return _base_result(
            normalized,
            settings,
            status="skipped",
            details="Only GET and HEAD performance tests are allowed.",
            error_type=None,
        )
    if has_unresolved_parameters(normalized["endpoint"]):
        return _base_result(
            normalized,
            settings,
            status="skipped",
            details="Dynamic endpoints with unresolved path parameters are skipped.",
            error_type=None,
        )

    locustfile_path = save_locustfile(run_id, normalized)
    artifacts = [locustfile_path]
    locust_result = run_locust_subprocess(
        locustfile_path=locustfile_path,
        target_url=target_url,
        users=settings["users"],
        spawn_rate=settings["spawn_rate"],
        duration_seconds=settings["duration_seconds"],
        run_id=run_id,
        test_id=normalized["id"],
    )
    csv_prefix = locust_result.get("csv_prefix")
    if csv_prefix:
        artifacts.extend(
            str(path)
            for path in [
                Path(f"{csv_prefix}_stats.csv"),
                Path(f"{csv_prefix}_failures.csv"),
                Path(f"{csv_prefix}_exceptions.csv"),
            ]
            if path.exists()
        )
    if locust_result.get("status") != "success":
        error_type = locust_result.get("error_type") or "environment_error"
        status = "configuration_error" if error_type == "configuration_error" else "environment_error"
        return _base_result(
            normalized,
            settings,
            status=status,
            details=str(locust_result.get("error") or "Locust run failed."),
            error_type=error_type,
            artifact_paths=artifacts,
        )

    parsed_metrics = parse_locust_csv(str(csv_prefix))
    metrics = parsed_metrics.get("metrics") or {}
    if parsed_metrics.get("error"):
        return _base_result(
            normalized,
            settings,
            status="environment_error",
            details=str(parsed_metrics["error"]),
            error_type="environment_error",
            artifact_paths=artifacts,
        )
    if _safe_int(metrics.get("total_requests"), 0) <= 0:
        return _base_result(
            normalized,
            settings,
            status="environment_error",
            details="No performance requests completed; target may be unavailable.",
            error_type="environment_error",
            artifact_paths=artifacts,
        )

    thresholds = evaluate_performance_thresholds(metrics, normalized, preferences)
    threshold_failed = any(not item.get("passed") for item in thresholds)
    status = "performance_threshold_failed" if threshold_failed else "passed"
    details = (
        "One or more performance thresholds failed."
        if threshold_failed
        else "Performance thresholds passed."
    )
    return {
        **_base_result(
            normalized,
            settings,
            status=status,
            details=details,
            error_type="performance_threshold_failed" if threshold_failed else None,
            artifact_paths=artifacts,
        ),
        **metrics,
        "threshold_results": thresholds,
    }


def compute_performance_summary(test_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute compact aggregate metrics for performance test execution."""

    total = len(test_results)
    passed = sum(1 for item in test_results if item.get("status") == "passed")
    skipped = sum(1 for item in test_results if item.get("status") == "skipped")
    errors = sum(
        1
        for item in test_results
        if item.get("status") in {"error", "environment_error", "configuration_error"}
    )
    failed = sum(
        1
        for item in test_results
        if item.get("status") in {"failed", "performance_threshold_failed"}
    )
    avg_values = [
        float(item["average_response_time_ms"])
        for item in test_results
        if item.get("average_response_time_ms") is not None
    ]
    p95_values = [
        float(item["p95_response_time_ms"])
        for item in test_results
        if item.get("p95_response_time_ms") is not None
    ]
    failure_rates = [
        float(item.get("failure_rate", 0.0))
        for item in test_results
        if item.get("failure_rate") is not None
    ]
    return {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "average_response_time_ms": round(sum(avg_values) / len(avg_values), 2)
        if avg_values
        else None,
        "p95_response_time_ms": round(sum(p95_values) / len(p95_values), 2)
        if p95_values
        else None,
        "overall_failure_rate": round(sum(failure_rates) / len(failure_rates), 2)
        if failure_rates
        else 0.0,
    }


def save_performance_result(
    run_id: str,
    performance_output: dict[str, Any],
    results_dir: str = "results",
) -> str:
    """Save results/runs/<run_id>/performance_result.json."""

    run_dir = ensure_directory(Path(results_dir) / "runs" / run_id)
    path = write_json_file(
        run_dir / "performance_result.json",
        json_safe(mask_sensitive_values(performance_output)),
    )
    return str(path)
