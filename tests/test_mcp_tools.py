"""Tests for MCP tool registry and executor (T10, T11)."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestMCPToolRegistry:
    """Verify tool registry structure."""

    def test_all_tools_present(self):
        from src.llm.tools import MCP_TOOLS
        names = {t["name"] for t in MCP_TOOLS}
        assert names == {
            "flox_search",
            "flox_show",
            "flox_validate_manifest",
            "flox_list_remote",
            "floxhub_env_metadata",
        }

    def test_tool_schemas_valid(self):
        from src.llm.tools import MCP_TOOLS
        for tool in MCP_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            schema = tool["input_schema"]
            assert schema["type"] == "object"
            assert "properties" in schema
            assert "required" in schema


class TestToolExecution:
    """Verify tool dispatch and error handling."""

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        from src.llm.tools import execute_tool
        result = await execute_tool("nonexistent_tool", {})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "Unknown tool" in parsed["error"]

    @pytest.mark.asyncio
    async def test_execute_flox_search_dispatches(self):
        from src.llm.tools import execute_tool
        with patch("src.mcp_server.server.flox_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [{"name": "python3", "version": "3.13"}]
            result = await execute_tool("flox_search", {"query": "python3"})
            parsed = json.loads(result)
            assert parsed == [{"name": "python3", "version": "3.13"}]
            mock_search.assert_awaited_once_with("python3")

    @pytest.mark.asyncio
    async def test_execute_tool_timeout(self):
        import asyncio
        from src.llm.tools import execute_tool

        async def slow_search(query):
            await asyncio.sleep(10)
            return []

        with patch("src.mcp_server.server.flox_search", side_effect=slow_search):
            result = await execute_tool("flox_search", {"query": "test"}, timeout=0.1)
            parsed = json.loads(result)
            assert "error" in parsed
            assert "timed out" in parsed["error"]


class TestManifestValidation:
    """Verify manifest validation tool."""

    @pytest.mark.asyncio
    async def test_valid_manifest(self):
        from src.mcp_server.server import flox_validate_manifest
        result = await flox_validate_manifest('version = 1\n[install]\npython3.pkg-path = "python3"')
        assert result["valid"] is True
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_invalid_toml(self):
        from src.mcp_server.server import flox_validate_manifest
        result = await flox_validate_manifest("this is not valid toml [[[")
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_missing_version(self):
        from src.mcp_server.server import flox_validate_manifest
        result = await flox_validate_manifest('[install]\npython3.pkg-path = "python3"')
        assert result["valid"] is False
        assert any("version" in e for e in result["errors"])
