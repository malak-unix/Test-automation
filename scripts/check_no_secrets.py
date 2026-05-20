"""Scan project text files for likely committed secrets.

The scanner intentionally ignores .env, virtual environments, caches, generated
run artifacts, and tests that verify masking behavior. It allows placeholders in
.env.example and documentation.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9_-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),
    re.compile(r"(?i)\b(GROQ_API_KEY|MISTRAL_API_KEY|GITHUB_TOKEN)\s*=\s*(?!your_|$)(.+)"),
]
IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ipynb_checkpoints",
    "results",
    "notebooks/results",
    "notebooks/reports",
    "reports/generated",
}
IGNORED_FILES = {
    ".env",
    "dashboard_stdout.log",
    "dashboard_stderr.log",
}
ALLOWED_PLACEHOLDER_FILES = {
    ".env.example",
    "README.md",
    "docs/demo_script.md",
    "docs/final_demo_guide.md",
}
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".j2",
    ".json",
    ".md",
    ".py",
    ".ps1",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def _is_ignored(path: Path) -> bool:
    relative = path.relative_to(ROOT).as_posix()
    if path.name in IGNORED_FILES:
        return True
    return any(relative == item or relative.startswith(f"{item}/") for item in IGNORED_DIRS)


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {".gitignore", ".env.example"}


def _is_allowed_placeholder(path: Path, line: str) -> bool:
    relative = path.relative_to(ROOT).as_posix()
    if relative in ALLOWED_PLACEHOLDER_FILES and (
        "your_" in line
        or line.strip().endswith("=<not configured>")
    ):
        return True
    if relative.startswith("tests/") and "SHOULD_NOT_APPEAR" in line:
        return True
    if path.name == "check_no_secrets.py":
        return True
    return False


def main() -> int:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or _is_ignored(path) or not _is_text_file(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _is_allowed_placeholder(path, line):
                continue
            for pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    relative = path.relative_to(ROOT).as_posix()
                    findings.append(f"{relative}:{line_number}: possible secret pattern")
                    break

    if findings:
        print("Potential secrets found:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("No likely committed secrets found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
