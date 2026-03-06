"""Tests for Codex LLM backend — code generation, tool-use loop."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.codex import call_codex, extract_code_blocks, estimate_code_confidence
from src.models.types import BuiltContext, SkillPackage


@pytest.fixture
def mock_codex_response():
    """Mock Anthropic response with code blocks."""
    response = MagicMock()
    text_block = MagicMock()
    text_block.text = "Here's the manifest:\n```toml\n[install.python3]\npkg-path = \"python3\"\n```"
    text_block.type = "text"
    response.content = [text_block]
    response.stop_reason = "end_turn"
    response.model = "claude-sonnet-4-6"
    response.usage = MagicMock(input_tokens=100, output_tokens=200)
    return response


@pytest.fixture
def sample_message():
    return {
        "message_id": "test-123",
        "content": {
            "text": "write a manifest with python3",
            "code_blocks": [],
        },
        "context": {},
    }


class TestCallCodex:
    @pytest.mark.asyncio
    async def test_returns_response_with_codex_backend(self, mock_codex_response, sample_message):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_codex_response)

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            result = await call_codex(sample_message, BuiltContext(), [])

        assert result["status"] == "ok"
        assert result["llm_backend"] == "codex"

    @pytest.mark.asyncio
    async def test_uses_code_focused_system_prompt(self, mock_codex_response, sample_message):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_codex_response)

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            await call_codex(sample_message, BuiltContext(), [])

        call_kwargs = mock_client.messages.create.call_args
        system_prompt = call_kwargs.kwargs["system"]
        assert "FloxBot Codex" in system_prompt
        assert "manifest.toml" in system_prompt

    @pytest.mark.asyncio
    async def test_extracts_code_blocks_from_response(self, mock_codex_response, sample_message):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_codex_response)

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            result = await call_codex(sample_message, BuiltContext(), [])

        assert len(result["code_blocks"]) >= 1
        assert "python3" in result["code_blocks"][0]

    @pytest.mark.asyncio
    async def test_handles_api_error(self, sample_message):
        import anthropic

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APIError(
                message="test error",
                request=MagicMock(),
                body=None,
            )
        )

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            result = await call_codex(sample_message, BuiltContext(), [])

        assert result["status"] == "error"
        assert result["llm_backend"] == "codex"

    @pytest.mark.asyncio
    async def test_skills_in_response(self, mock_codex_response, sample_message):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_codex_response)

        skills = [SkillPackage(name="python", role="primary", skill_md="# Python")]
        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            result = await call_codex(sample_message, BuiltContext(), skills)

        assert len(result["skills_used"]) == 1
        assert result["skills_used"][0]["name"] == "python"


class TestExtractCodeBlocks:
    def test_extracts_toml_block(self):
        text = "```toml\n[install]\npython3 = {}\n```"
        blocks = extract_code_blocks(text)
        assert len(blocks) == 1
        assert "python3" in blocks[0]

    def test_extracts_multiple_blocks(self):
        text = "```bash\nflox install hello\n```\nand\n```toml\n[hook]\non-activate = 'echo hi'\n```"
        blocks = extract_code_blocks(text)
        assert len(blocks) == 2

    def test_no_blocks(self):
        text = "Just plain text, no code."
        blocks = extract_code_blocks(text)
        assert blocks == []


class TestCodeConfidence:
    def test_higher_with_code_blocks(self):
        score_with = estimate_code_confidence("```\ncode\n```", BuiltContext(), ["code"])
        score_without = estimate_code_confidence("no code here", BuiltContext(), [])
        assert score_with > score_without

    def test_boosted_by_rag_results(self):
        ctx = BuiltContext(rag_results=[{"content": "test"}])
        score = estimate_code_confidence("test", ctx, [])
        assert score > 0.4

    def test_reduced_by_hedging(self):
        score = estimate_code_confidence("I'm not sure this will work", BuiltContext(), [])
        assert score < 0.4

    def test_bounded_0_to_1(self):
        ctx = BuiltContext(
            rag_results=[{"content": "a"}] * 5,
            skills=[SkillPackage(name="test")],
        )
        score = estimate_code_confidence("```\ncode\n```", ctx, ["code"])
        assert 0.0 <= score <= 1.0
