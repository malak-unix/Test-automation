"""Configuration loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _safe_default_config() -> dict[str, Any]:
    return {
        "project": {
            "name": "SMA Test Automation",
            "default_execution_mode": "sequential",
        },
        "testing": {
            "default_test_types": ["api"],
            "max_duration_minutes": 5,
        },
        "results": {
            "base_dir": "results",
        },
        "llm": {
            "provider_env_var": "LLM_PROVIDER",
            "groq_api_key_env_var": "GROQ_API_KEY",
            "mistral_api_key_env_var": "MISTRAL_API_KEY",
        },
    }


def load_yaml_config(path: str) -> dict[str, Any]:
    """Load a YAML config file and return an empty dict for empty files."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def load_default_config() -> dict[str, Any]:
    """Load config/config.example.yml, or return safe defaults if absent."""

    project_root = Path(__file__).resolve().parents[3]
    config_path = project_root / "config" / "config.example.yml"
    if config_path.exists():
        return load_yaml_config(str(config_path))
    return _safe_default_config()
