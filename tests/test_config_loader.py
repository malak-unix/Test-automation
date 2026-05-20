from __future__ import annotations

import json

from test_auto.shared.config_loader import load_default_config
from test_auto.shared.secrets import get_llm_config


def test_load_default_config_returns_dict() -> None:
    assert isinstance(load_default_config(), dict)


def test_get_llm_config_does_not_expose_actual_key_values(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "secret-groq-value")
    monkeypatch.setenv("MISTRAL_API_KEY", "secret-mistral-value")

    config = get_llm_config()
    serialized = json.dumps(config)

    assert "secret-groq-value" not in serialized
    assert "secret-mistral-value" not in serialized


def test_get_llm_config_returns_key_booleans(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "secret-groq-value")
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    config = get_llm_config()

    assert isinstance(config["has_groq_key"], bool)
    assert isinstance(config["has_mistral_key"], bool)
    assert config["has_groq_key"] is True
    assert config["has_mistral_key"] is False
