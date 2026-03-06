"""Tests for Co-Pilot chat mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.modes.chat import _build_chat_message, _get_response


class TestBuildChatMessage:
    def test_basic_message(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        msg = _build_chat_message("hello", "conv_123", 3)
        assert msg["content"]["text"] == "hello"
        assert msg["context"]["conversation_id"] == "conv_123"
        assert msg["session"]["prior_messages"] == 3
        assert msg["session"]["copilot_active"] is True


class TestGetResponse:
    @pytest.mark.asyncio
    async def test_online_response(self, tmp_path):
        mock_client = AsyncMock()
        mock_client.post_message = AsyncMock(return_value={"text": "Hello from FloxBot!"})

        from src.local.chroma_store import ChromaStore
        chroma = ChromaStore(persist_dir=str(tmp_path / "chroma"))

        messages = [{"role": "user", "content": "hello"}]
        result = await _get_response("hello", messages, "conv_1", mock_client, chroma)
        assert result == "Hello from FloxBot!"

    @pytest.mark.asyncio
    async def test_offline_with_data(self, tmp_path):
        from src.local.chroma_store import ChromaStore
        chroma = ChromaStore(persist_dir=str(tmp_path / "chroma"))
        chroma.add_chunks(ids=["c1"], documents=["Flox helps manage dev environments"])

        messages = [{"role": "user", "content": "what is flox?"}]
        result = await _get_response("what is flox?", messages, "conv_1", None, chroma)
        assert "(Offline)" in result
        assert "Flox" in result

    @pytest.mark.asyncio
    async def test_offline_no_data(self, tmp_path):
        from src.local.chroma_store import ChromaStore
        chroma = ChromaStore(persist_dir=str(tmp_path / "chroma"))

        messages = [{"role": "user", "content": "anything"}]
        result = await _get_response("anything", messages, "conv_1", None, chroma)
        assert "copilot-sync" in result.lower()

    @pytest.mark.asyncio
    async def test_api_failure_falls_back(self, tmp_path):
        mock_client = AsyncMock()
        mock_client.post_message = AsyncMock(side_effect=ConnectionError("down"))

        from src.local.chroma_store import ChromaStore
        chroma = ChromaStore(persist_dir=str(tmp_path / "chroma"))

        messages = [{"role": "user", "content": "test"}]
        result = await _get_response("test", messages, "conv_1", mock_client, chroma)
        assert "offline" in result.lower() or "no local" in result.lower()


class TestMultiTurn:
    @pytest.mark.asyncio
    async def test_message_includes_prior_count(self, tmp_path, monkeypatch):
        """Chat messages track prior_messages count."""
        monkeypatch.chdir(tmp_path)
        msg1 = _build_chat_message("first", "conv_1", 0)
        assert msg1["session"]["prior_messages"] == 0

        msg2 = _build_chat_message("second", "conv_1", 2)
        assert msg2["session"]["prior_messages"] == 2
