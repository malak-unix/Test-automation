"""Safe environment helpers for future LLM providers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def load_env_file() -> None:
    """Load environment variables from .env without printing any values."""

    env_path = Path.cwd() / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)


def get_env_value(name: str, default: str | None = None) -> str | None:
    """Read one environment variable without logging it."""

    return os.getenv(name, default)


def get_llm_config() -> dict[str, Any]:
    """Return non-secret LLM configuration readiness flags."""

    load_env_file()
    groq_key = get_env_value("GROQ_API_KEY")
    mistral_key = get_env_value("MISTRAL_API_KEY")
    return {
        "provider": get_env_value("LLM_PROVIDER", "groq"),
        "has_groq_key": bool(groq_key),
        "has_mistral_key": bool(mistral_key),
        "groq_model": get_env_value("GROQ_MODEL"),
        "mistral_model": get_env_value("MISTRAL_MODEL"),
    }
