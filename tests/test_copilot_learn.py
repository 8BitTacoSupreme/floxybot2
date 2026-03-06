"""Tests for Co-Pilot learn mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.modes.learn import async_learn, _suggest_topic, _build_learn_message


class TestSuggestTopic:
    def test_beginner_first_topic(self):
        topic = _suggest_topic("beginner", [])
        assert "Getting started" in topic

    def test_skips_completed_topics(self):
        topic = _suggest_topic("beginner", ["Getting started with Flox environments"])
        assert topic != "Getting started with Flox environments"

    def test_intermediate_topic(self):
        topic = _suggest_topic("intermediate", [])
        assert "Advanced" in topic or "hooks" in topic.lower() or "workflow" in topic.lower() or "Building" in topic

    def test_advanced_topic(self):
        topic = _suggest_topic("advanced", [])
        assert "Custom" in topic or "CI/CD" in topic or "Composable" in topic or "Contributing" in topic


class TestBuildLearnMessage:
    def test_basic_message(self):
        msg = _build_learn_message("Flox basics", "beginner")
        assert "Flox basics" in msg["content"]["text"]
        assert "beginner" in msg["content"]["text"]
        assert msg["context"]["channel_metadata"]["mode"] == "learn"


class TestAsyncLearn:
    @pytest.mark.asyncio
    async def test_online_success(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        mock_client = AsyncMock()
        mock_client.post_message = AsyncMock(return_value={
            "text": "Lesson: Flox is a package manager..."
        })
        mock_client.get_memory = AsyncMock(return_value={})
        mock_client.close = AsyncMock()

        with patch("src.api_client.CopilotAPIClient", return_value=mock_client):
            result = await async_learn(topic="Flox basics", api_url="http://test:8000")

        assert "Lesson" in result or "Flox" in result

    @pytest.mark.asyncio
    async def test_offline_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        result = await async_learn(topic="Flox basics", offline=True)
        assert "requires API" in result.lower() or "copilot-sync" in result.lower()
