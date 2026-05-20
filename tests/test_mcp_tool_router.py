from __future__ import annotations

import json

from test_auto.mcp.tool_router import (
    build_mcp_agent_log,
    call_mcp_or_local,
    should_use_mcp,
)


def test_should_use_mcp_false_by_default() -> None:
    assert should_use_mcp() is False


def test_should_use_mcp_true_from_user_preferences() -> None:
    assert should_use_mcp({"use_mcp_tools": True}) is True


def test_should_use_mcp_true_from_config() -> None:
    assert should_use_mcp(config={"mcp": {"enabled": True}}) is True


def test_call_mcp_or_local_uses_local_when_disabled() -> None:
    result = call_mcp_or_local(
        tool_name="demo_tool",
        mcp_args={},
        local_callable=lambda value: {"value": value},
        local_args={"value": 7},
        user_preferences={"use_mcp_tools": False},
    )

    assert result["used_mcp"] is False
    assert result["result"] == {"value": 7}
    assert result["fallback_used"] is False


def test_call_mcp_or_local_falls_back_when_mcp_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "test_auto.mcp.tool_router.invoke_mcp_tool_sync",
        lambda *args, **kwargs: {
            "status": "error",
            "tool_name": "demo_tool",
            "result": None,
            "error": "server unavailable",
        },
    )

    result = call_mcp_or_local(
        tool_name="demo_tool",
        mcp_args={},
        local_callable=lambda: {"fallback": True},
        local_args={},
        user_preferences={"use_mcp_tools": True},
    )

    assert result["used_mcp"] is False
    assert result["fallback_used"] is True
    assert result["result"] == {"fallback": True}


def test_build_mcp_agent_log_contains_no_secrets() -> None:
    log = build_mcp_agent_log(
        "send_http_request_tool",
        used_mcp=False,
        fallback_used=True,
        error="Bearer SECRET_TOKEN_SHOULD_NOT_APPEAR",
    )

    assert "SECRET_TOKEN_SHOULD_NOT_APPEAR" not in json.dumps(log)
