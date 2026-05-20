from __future__ import annotations

import json
from pathlib import Path

from test_auto.mcp.mcp_config import (
    get_default_mcp_server_command,
    load_mcp_config,
    sanitize_mcp_config_for_display,
)
from test_auto.mcp.testing_mcp_client import (
    list_testing_mcp_tool_names,
    run_mcp_health_check_sync,
)


def test_get_default_mcp_server_command() -> None:
    config = get_default_mcp_server_command()

    assert config["testing"]["transport"] == "stdio"
    assert "testing_tools_server.py" in config["testing"]["args"][0]


def test_load_mcp_config_default() -> None:
    config = load_mcp_config()

    assert config["testing"]["command"] == "python"


def test_load_mcp_config_from_file(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(
        json.dumps(
            {
                "testing": {
                    "command": "python",
                    "args": ["mcp_servers/testing_tools_server.py"],
                    "transport": "stdio",
                }
            }
        ),
        encoding="utf-8",
    )

    config = load_mcp_config(str(path))

    assert config["testing"]["transport"] == "stdio"


def test_sanitize_mcp_config_for_display_masks_secrets() -> None:
    sanitized = sanitize_mcp_config_for_display(
        {
            "testing": {
                "command": "python",
                "args": ["server.py"],
                "transport": "stdio",
                "Authorization": "Bearer SECRET_TOKEN_SHOULD_NOT_APPEAR",
                "token": "SECRET_TOKEN_SHOULD_NOT_APPEAR",
            }
        }
    )

    assert "SECRET_TOKEN_SHOULD_NOT_APPEAR" not in json.dumps(sanitized)


def test_list_testing_mcp_tool_names_function_exists() -> None:
    assert callable(list_testing_mcp_tool_names)


def test_run_mcp_health_check_sync_handles_event_loop_safely() -> None:
    result = run_mcp_health_check_sync()

    assert result.get("status") in {"ok", "error", "instruction"}
