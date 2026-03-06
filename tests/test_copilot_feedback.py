"""Tests for Co-Pilot feedback mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.modes.feedback import async_feedback


class TestAsyncFeedback:
    @pytest.mark.asyncio
    async def test_submit_feedback(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        result = await async_feedback(
            offline=True,
            category="helpful",
            detail="Great explanation of environments!",
        )
        assert result["status"] == "ok"
        assert "feedback_id" in result

        # Check JSONL queue
        from src.local.jsonl_queue import JSONLQueue
        q = JSONLQueue(tmp_path / "feedback.jsonl")
        records = q.read_all()
        assert len(records) == 1
        assert records[0]["category"] == "helpful"

    @pytest.mark.asyncio
    async def test_submit_feedback_online(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        mock_client = AsyncMock()
        mock_client.post_feedback = AsyncMock(return_value={"status": "ok"})
        mock_client.close = AsyncMock()

        with patch("src.api_client.CopilotAPIClient", return_value=mock_client):
            result = await async_feedback(
                api_url="http://test:8000",
                category="incorrect",
                detail="Wrong version mentioned",
            )

        assert result["status"] == "ok"
        mock_client.post_feedback.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_detail_cancels(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        result = await async_feedback(
            offline=True,
            category="helpful",
            detail="",
        )
        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_all_categories(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        for cat in ["incorrect", "incomplete", "outdated", "confusing", "helpful", "other"]:
            result = await async_feedback(offline=True, category=cat, detail=f"Test {cat}")
            assert result["status"] == "ok"
