"""Validate optional Groq/Mistral planner configuration safely.

The script never prints raw API keys and never calls an LLM API. Missing keys
are valid because deterministic planning is the default project mode.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from test_auto.planning.llm_planner import get_planner_llm_config
from test_auto.shared.secrets import get_llm_config


def main() -> int:
    """Print non-secret LLM readiness flags."""

    try:
        raw_config = get_llm_config()
        planner_config = get_planner_llm_config()
    except Exception as error:
        print(f"LLM config validation failed: {error.__class__.__name__}")
        return 1

    print("LLM configuration validation")
    print(f"selected_provider={raw_config.get('provider') or 'none'}")
    print(f"has_groq_key={bool(raw_config.get('has_groq_key'))}")
    print(f"has_mistral_key={bool(raw_config.get('has_mistral_key'))}")
    print(f"configured_groq_model={raw_config.get('groq_model') or '<not configured>'}")
    print(f"configured_mistral_model={raw_config.get('mistral_model') or '<not configured>'}")
    print(f"planner_provider={planner_config.get('provider')}")
    print(f"planner_model={planner_config.get('model') or '<not configured>'}")
    print(f"llm_planning_available={bool(planner_config.get('available'))}")
    print("status=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
