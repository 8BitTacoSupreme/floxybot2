"""Tests for Co-Pilot ask mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.modes.ask import async_ask, _build_message, _detect_project_context


class TestBuildMessage:
    def test_basic_message(self):
        msg = _build_message("How do I install python?")
        assert msg["content"]["text"] == "How do I install python?"
        assert msg["user_identity"]["channel"] == "copilot"
        assert msg["session"]["copilot_active"] is True

    def test_project_context_no_flox(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctx = _detect_project_context()
        assert ctx["has_flox_env"] is False

    def test_project_context_with_flox(self, tmp_path, monkeypatch):
        flox_dir = tmp_path / ".flox" / "env"
        flox_dir.mkdir(parents=True)
        (flox_dir / "manifest.toml").write_text('[install]\npython3.pkg-path = "python3"\n')
        monkeypatch.chdir(tmp_path)
        ctx = _detect_project_context()
        assert ctx["has_flox_env"] is True
        assert "python3" in ctx["manifest"]


class TestAsyncAsk:
    @pytest.mark.asyncio
    async def test_online_success(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        mock_client_instance = AsyncMock()
        mock_client_instance.post_message = AsyncMock(return_value={
            "text": "Use `flox install python3`.",
            "message_id": "msg_123",
            "status": "ok",
        })
        mock_client_instance.close = AsyncMock()

        with patch("src.api_client.CopilotAPIClient", return_value=mock_client_instance):
            with patch("builtins.input", return_value="skip"):
                answer = await async_ask("How do I install python?", api_url="http://test:8000")

        assert "flox install" in answer
        mock_client_instance.post_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_offline_with_local_data(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        from src.local.chroma_store import ChromaStore
        chroma = ChromaStore(persist_dir=str(tmp_path / "chroma"))
        chroma.add_chunks(
            ids=["c1"],
            documents=["To install python, use: flox install python3"],
            metadatas=[{"skill_name": "core-canon", "heading": "Install"}],
        )

        answer = await async_ask("install python", api_url="http://test:8000", offline=True)
        assert "flox install" in answer.lower() or "install" in answer.lower()

    @pytest.mark.asyncio
    async def test_offline_no_data(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        answer = await async_ask("how do I fly?", api_url="http://test:8000", offline=True)
        assert "copilot-sync" in answer.lower() or "no local" in answer.lower()

    @pytest.mark.asyncio
    async def test_api_failure_falls_back(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        mock_client_instance = AsyncMock()
        mock_client_instance.post_message = AsyncMock(side_effect=ConnectionError("offline"))
        mock_client_instance.close = AsyncMock()

        with patch("src.api_client.CopilotAPIClient", return_value=mock_client_instance):
            answer = await async_ask("test question", api_url="http://test:8000")

        assert "no local" in answer.lower() or "copilot-sync" in answer.lower()
