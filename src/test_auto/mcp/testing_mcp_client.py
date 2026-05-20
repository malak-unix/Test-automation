"""Async client helpers for the standalone testing tools MCP server."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from test_auto.mcp.mcp_config import load_mcp_config
from test_auto.tools.bug_tools import mask_sensitive_values


async def get_testing_mcp_tools(config_path: str | None = None) -> list[Any]:
    """Discover tools exposed by the testing MCP server."""

    client = MultiServerMCPClient(load_mcp_config(config_path))
    tools = await client.get_tools()
    return list(tools)


async def list_testing_mcp_tool_names(config_path: str | None = None) -> list[str]:
    """Return names of tools exposed by the testing MCP server."""

    tools = await get_testing_mcp_tools(config_path)
    return sorted(str(getattr(tool, "name", "")) for tool in tools if getattr(tool, "name", ""))


async def _invoke_tool(tool: Any, payload: dict[str, Any]) -> Any:
    if hasattr(tool, "ainvoke"):
        return await tool.ainvoke(payload)
    if hasattr(tool, "invoke"):
        return tool.invoke(payload)
    if callable(tool):
        return tool(**payload)
    raise TypeError("Tool object is not invokable.")


async def run_mcp_health_check(config_path: str | None = None) -> dict[str, Any]:
    """Invoke the health_check MCP tool and return its result."""

    try:
        tools = await get_testing_mcp_tools(config_path)
        health_tools = [tool for tool in tools if getattr(tool, "name", "") == "health_check"]
        if not health_tools:
            return {"status": "error", "error": "health_check tool was not discovered."}
        result = await _invoke_tool(health_tools[0], {})
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict) and "text" in first:
                try:
                    return mask_sensitive_values(json.loads(first["text"]))
                except json.JSONDecodeError:
                    return mask_sensitive_values({"status": "ok", "content": result})
        if isinstance(result, str):
            try:
                return mask_sensitive_values(json.loads(result))
            except json.JSONDecodeError:
                return mask_sensitive_values({"status": "ok", "content": result})
        if isinstance(result, dict):
            return mask_sensitive_values(result)
        return mask_sensitive_values({"status": "ok", "content": result})
    except Exception as error:
        return {"status": "error", "error": str(error)}


def run_mcp_health_check_sync(config_path: str | None = None) -> dict[str, Any]:
    """Run the MCP health check from synchronous code."""

    try:
        asyncio.get_running_loop()
        return {
            "status": "instruction",
            "message": "Use await run_mcp_health_check(...) in notebooks.",
        }
    except RuntimeError:
        return asyncio.run(run_mcp_health_check(config_path))
