"""Configuration helpers for the standalone MCP testing tools server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_auto.tools.bug_tools import mask_sensitive_values


def get_default_mcp_server_command() -> dict[str, Any]:
    """Return the default stdio MCP server configuration."""

    return {
        "testing": {
            "command": "python",
            "args": ["mcp_servers/testing_tools_server.py"],
            "transport": "stdio",
        }
    }


def _validate_server_config(name: str, server: dict[str, Any]) -> None:
    missing = [key for key in ("command", "args", "transport") if key not in server]
    if missing:
        raise ValueError(f"MCP server '{name}' is missing required keys: {', '.join(missing)}")
    if server["transport"] != "stdio":
        raise ValueError(f"MCP server '{name}' must use stdio transport in this milestone.")


def load_mcp_config(path: str | None = None) -> dict[str, Any]:
    """Load MCP config from JSON or return the default no-secret config."""

    if path and Path(path).exists():
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    else:
        data = get_default_mcp_server_command()
    if not isinstance(data, dict) or not data:
        raise ValueError("MCP config must be a non-empty object.")
    for name, server in data.items():
        if not isinstance(server, dict):
            raise ValueError(f"MCP server '{name}' config must be an object.")
        _validate_server_config(name, server)
    return data


def sanitize_mcp_config_for_display(config: dict[str, Any]) -> dict[str, Any]:
    """Mask token-like values before displaying MCP configuration."""

    return mask_sensitive_values(config)
