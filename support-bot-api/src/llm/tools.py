"""MCP Tool Registry and Executor for Anthropic tool-use protocol."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Anthropic tool-use JSON schemas for all MCP tools
MCP_TOOLS = [
    {
        "name": "flox_search",
        "description": "Search the Flox package catalog. Returns matching packages with names, versions, and descriptions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The package name or search term to look up in the Flox catalog.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "flox_show",
        "description": "Show detailed information about a specific Flox package, including available versions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "package": {
                    "type": "string",
                    "description": "The fully qualified package name (e.g. 'python3', 'nodejs').",
                },
            },
            "required": ["package"],
        },
    },
    {
        "name": "flox_validate_manifest",
        "description": "Validate a Flox manifest.toml for correctness. Returns validation errors if any.",
        "input_schema": {
            "type": "object",
            "properties": {
                "manifest_content": {
                    "type": "string",
                    "description": "The full contents of a manifest.toml file to validate.",
                },
            },
            "required": ["manifest_content"],
        },
    },
    {
        "name": "flox_list_remote",
        "description": "List packages installed in a remote FloxHub environment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "env_ref": {
                    "type": "string",
                    "description": "The FloxHub environment reference (e.g. 'owner/envname').",
                },
            },
            "required": ["env_ref"],
        },
    },
    {
        "name": "floxhub_env_metadata",
        "description": "Get metadata about a FloxHub environment, including installed packages and configuration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "env_ref": {
                    "type": "string",
                    "description": "The FloxHub environment reference (e.g. 'owner/envname').",
                },
            },
            "required": ["env_ref"],
        },
    },
]

# Dispatcher mapping tool names to MCP server functions
_TOOL_DISPATCH: dict[str, str] = {
    "flox_search": "flox_search",
    "flox_show": "flox_show",
    "flox_validate_manifest": "flox_validate_manifest",
    "flox_list_remote": "flox_list_remote",
    "floxhub_env_metadata": "floxhub_env_metadata",
}


async def execute_tool(name: str, tool_input: dict[str, Any], timeout: int = 15) -> str:
    """Execute an MCP tool by name and return the JSON result string.

    Wraps each call with asyncio.wait_for for timeout protection.
    """
    from src.mcp_server.server import (
        flox_search,
        flox_show,
        flox_validate_manifest,
        flox_list_remote,
        floxhub_env_metadata,
    )

    dispatch = {
        "flox_search": lambda: flox_search(tool_input["query"]),
        "flox_show": lambda: flox_show(tool_input["package"]),
        "flox_validate_manifest": lambda: flox_validate_manifest(tool_input["manifest_content"]),
        "flox_list_remote": lambda: flox_list_remote(tool_input["env_ref"]),
        "floxhub_env_metadata": lambda: floxhub_env_metadata(tool_input["env_ref"]),
    }

    handler = dispatch.get(name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        result = await asyncio.wait_for(handler(), timeout=timeout)
        return json.dumps(result, default=str)
    except asyncio.TimeoutError:
        logger.warning("Tool %s timed out after %ds", name, timeout)
        return json.dumps({"error": f"Tool {name} timed out after {timeout}s"})
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e)
        return json.dumps({"error": f"Tool {name} failed: {str(e)}"})
