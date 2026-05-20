"""Validate a GitHub repository URL for demo input.

Public repositories do not require a GitHub token. If GITHUB_TOKEN is present,
this script reports only that a token is configured and never prints the value.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from test_auto.shared.secrets import get_env_value, load_env_file
from test_auto.tools.repo_tools import is_probably_git_url


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a GitHub repository URL safely.")
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    return parser.parse_args()


def _git_ls_remote(repo_url: str, timeout_seconds: int) -> tuple[bool, str]:
    if not shutil.which("git"):
        return False, "git executable not found"
    try:
        completed = subprocess.run(
            ["git", "ls-remote", repo_url],
            capture_output=True,
            text=True,
            timeout=max(1, min(timeout_seconds, 60)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "git ls-remote timed out"
    except OSError as error:
        return False, error.__class__.__name__
    if completed.returncode == 0:
        return True, "git ls-remote succeeded"
    stderr = (completed.stderr or completed.stdout or "").strip()
    first_line = stderr.splitlines()[0] if stderr else "git ls-remote failed"
    return False, first_line[:200]


def main() -> int:
    args = _parse_args()
    load_env_file()
    repo_url = args.repo_url.strip()
    is_valid_url = is_probably_git_url(repo_url)
    token_configured = bool(get_env_value("GITHUB_TOKEN"))
    git_accessible = False
    details = "URL was not checked because it is invalid."

    if is_valid_url:
        git_accessible, details = _git_ls_remote(repo_url, args.timeout_seconds)

    payload = {
        "repo_url": repo_url,
        "is_valid_url": is_valid_url,
        "git_accessible": git_accessible,
        "token_configured": token_configured,
        "details": details,
    }
    print(json.dumps(payload, indent=2))
    return 0 if is_valid_url else 1


if __name__ == "__main__":
    raise SystemExit(main())
