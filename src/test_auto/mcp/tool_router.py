"""Optional routing between local Python tools and MCP tools."""

from __future__ import annotations

from typing import Any, Callable

from test_auto.mcp.safe_mcp_invoker import invoke_mcp_tool_sync
from test_auto.tools.bug_tools import mask_sensitive_values


def should_use_mcp(
    user_preferences: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> bool:
    """Return True only when MCP tool usage is explicitly enabled."""

    preferences = user_preferences or {}
    if bool(preferences.get("use_mcp_tools")):
        return True
    mcp_config = (config or {}).get("mcp") or {}
    return bool(mcp_config.get("enabled"))


def _call_local(local_callable: Callable[..., Any], local_args: dict[str, Any]) -> dict[str, Any]:
    try:
        return {
            "used_mcp": False,
            "status": "success",
            "result": local_callable(**(local_args or {})),
            "fallback_used": False,
            "error": None,
        }
    except Exception as error:
        safe_error = mask_sensitive_values({"error": str(error)}).get("error")
        return {
            "used_mcp": False,
            "status": "error",
            "result": None,
            "fallback_used": False,
            "error": safe_error,
        }


def _mcp_tool_result_is_error(result: Any) -> bool:
    return isinstance(result, dict) and result.get("status") == "error"


def call_mcp_or_local(
    tool_name: str,
    mcp_args: dict[str, Any],
    local_callable: Callable[..., Any],
    local_args: dict[str, Any],
    user_preferences: dict[str, Any] | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Call an MCP tool when enabled, otherwise use the local callable."""

    if not should_use_mcp(user_preferences=user_preferences):
        return _call_local(local_callable, local_args)

    mcp_result = invoke_mcp_tool_sync(tool_name, mcp_args, config_path=config_path)
    inner_result = mcp_result.get("result")
    if mcp_result.get("status") == "success" and not _mcp_tool_result_is_error(inner_result):
        return {
            "used_mcp": True,
            "status": "success",
            "result": inner_result,
            "fallback_used": False,
            "error": None,
        }

    fallback = _call_local(local_callable, local_args)
    fallback.update(
        {
            "used_mcp": False,
            "fallback_used": True,
            "mcp_error": mcp_result.get("error")
            or (inner_result or {}).get("error")
            or "MCP tool call failed.",
        }
    )
    return fallback


def build_mcp_agent_log(
    tool_name: str,
    used_mcp: bool,
    fallback_used: bool,
    error: str | None = None,
) -> dict[str, Any]:
    """Build a compact, secret-safe metadata event for MCP tool routing."""

    return mask_sensitive_values(
        {
            "tool_name": tool_name,
            "used_mcp": bool(used_mcp),
            "fallback_used": bool(fallback_used),
            "error": error,
        }
    )
