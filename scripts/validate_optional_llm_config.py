"""Backward-compatible wrapper for LLM config validation."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_llm_config import main


if __name__ == "__main__":
    raise SystemExit(main())
