"""Safe invocation helpers for optional MCP tool usage."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from test_auto.mcp.testing_mcp_client import get_testing_mcp_tools
from test_auto.tools.bug_tools import mask_sensitive_values


def _safe_error_message(error: Exception) -> str:
    return str(mask_sensitive_values({"error": str(error)}).get("error"))


def _normalize_mcp_result(value: Any) -> Any:
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict) and "text" in first:
            try:
                return json.loads(first["text"])
            except json.JSONDecodeError:
                return {"content": value}
        if hasattr(first, "text"):
            try:
                return json.loads(first.text)
            except (TypeError, json.JSONDecodeError):
                return {"content": str(first.text)}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"content": value}
    return value


async def _invoke_tool(tool: Any, args: dict[str, Any]) -> Any:
    if hasattr(tool, "ainvoke"):
        return await tool.ainvoke(args)
    if hasattr(tool, "invoke"):
        return tool.invoke(args)
    if callable(tool):
        return tool(**args)
    raise TypeError("MCP tool object is not invokable.")


async def safe_ainvoke_mcp_tool(
    tool_name: str,
    args: dict[str, Any],
    config_path: str | None = None,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    """Invoke one MCP tool and return a masked, non-throwing result."""

    try:
        tools = await asyncio.wait_for(
            get_testing_mcp_tools(config_path),
            timeout=max(1, timeout_seconds),
        )
        matching = [tool for tool in tools if getattr(tool, "name", "") == tool_name]
        if not matching:
            return {
                "status": "error",
                "tool_name": tool_name,
                "result": None,
                "error": f"MCP tool '{tool_name}' was not discovered.",
            }
        raw_result = await asyncio.wait_for(
            _invoke_tool(matching[0], args or {}),
            timeout=max(1, timeout_seconds),
        )
        return {
            "status": "success",
            "tool_name": tool_name,
            "result": mask_sensitive_values(_normalize_mcp_result(raw_result)),
            "error": None,
        }
    except Exception as error:
        return {
            "status": "error",
            "tool_name": tool_name,
            "result": None,
            "error": _safe_error_message(error),
        }


def invoke_mcp_tool_sync(
    tool_name: str,
    args: dict[str, Any],
    config_path: str | None = None,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    """Invoke one MCP tool from synchronous agent code."""

    try:
        asyncio.get_running_loop()
        return {
            "status": "error",
            "tool_name": tool_name,
            "result": None,
            "error": "Cannot use sync MCP invocation inside an active event loop; use async version.",
        }
    except RuntimeError:
        return asyncio.run(
            safe_ainvoke_mcp_tool(
                tool_name=tool_name,
                args=args,
                config_path=config_path,
                timeout_seconds=timeout_seconds,
            )
        )


def mcp_available(config_path: str | None = None) -> bool:
    """Return True when the testing MCP server health check succeeds."""

    result = invoke_mcp_tool_sync("health_check", {}, config_path=config_path)
    payload = result.get("result") or {}
    return result.get("status") == "success" and payload.get("status") == "ok"
