"""Tests for Claude tool-use integration (T11)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.types import BuiltContext, SkillPackage


@pytest.fixture
def mock_claude_with_tool_use():
    """Mock Claude to first request a tool, then return final answer."""
    # First response: tool_use
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tool_123"
    tool_block.name = "flox_search"
    tool_block.input = {"query": "python3"}

    first_response = MagicMock()
    first_response.content = [tool_block]
    first_response.stop_reason = "tool_use"

    # Second response: final text
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Python 3.13 is available via `flox install python3`."

    second_response = MagicMock()
    second_response.content = [text_block]
    second_response.stop_reason = "end_turn"

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=[first_response, second_response])

    with patch("anthropic.AsyncAnthropic", return_value=mock_client) as patched:
        patched._mock_client = mock_client
        yield patched


class TestToolUseLoop:
    """Verify the Claude tool-use loop."""

    @pytest.mark.asyncio
    async def test_tool_use_round_trip(self, mock_claude_with_tool_use):
        """Claude requests flox_search → gets result → produces final answer."""
        from src.llm.claude import call_claude
        from src.llm.tools import execute_tool

        context = BuiltContext()
        message = {
            "message_id": "test-123",
            "content": {"text": "What versions of python are available?", "code_blocks": []},
        }

        with patch("src.llm.claude.execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = '[{"name": "python3", "version": "3.13"}]'
            result = await call_claude(message, context, skills=[], intent="conversational")

        assert result["status"] == "ok"
        assert "python3" in result["text"].lower() or "Python" in result["text"]
        mock_exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_tool_use_passthrough(self, mock_claude):
        """When Claude doesn't request tools, response passes through directly."""
        from src.llm.claude import call_claude

        context = BuiltContext()
        message = {
            "message_id": "test-456",
            "content": {"text": "Hello!", "code_blocks": []},
        }

        result = await call_claude(message, context, skills=[], intent="conversational")
        assert result["status"] == "ok"
        assert result["text"] == "This is a test response from Claude."
