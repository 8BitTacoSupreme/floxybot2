"""Tests for Co-Pilot ticket mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.modes.ticket import async_ticket, _auto_priority, _gather_context_bundle


class TestAutoPriority:
    def test_urgent_keywords(self):
        assert _auto_priority("Production crash", "") == "urgent"
        assert _auto_priority("Data loss issue", "") == "urgent"
        assert _auto_priority("Security vulnerability", "") == "urgent"

    def test_high_keywords(self):
        assert _auto_priority("Build error", "") == "high"
        assert _auto_priority("Cannot install packages", "") == "high"

    def test_low_keywords(self):
        assert _auto_priority("Just a question", "") == "low"
        assert _auto_priority("Minor suggestion", "") == "low"

    def test_normal_default(self):
        assert _auto_priority("Help with configuration", "") == "normal"


class TestGatherContextBundle:
    def test_no_flox_env(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bundle = _gather_context_bundle(tmp_path)
        assert "timestamp" in bundle
        assert "manifest" not in bundle

    def test_with_flox_env(self, tmp_path, monkeypatch):
        flox_dir = tmp_path / ".flox" / "env"
        flox_dir.mkdir(parents=True)
        (flox_dir / "manifest.toml").write_text("[install]\npython3 = {}\n")
        monkeypatch.chdir(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "Active"
            bundle = _gather_context_bundle(tmp_path)

        assert "manifest" in bundle
        assert "python3" in bundle["manifest"]


class TestAsyncTicket:
    @pytest.mark.asyncio
    async def test_create_ticket_offline(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = await async_ticket(
            offline=True,
            title="Test ticket",
            description="Testing ticket creation",
        )
        assert result["status"] == "queued"
        assert "ticket_id" in result

        # Check JSONL queue
        from src.local.jsonl_queue import JSONLQueue
        q = JSONLQueue(tmp_path / "tickets.jsonl")
        records = q.read_all()
        assert len(records) == 1
        assert records[0]["title"] == "Test ticket"

    @pytest.mark.asyncio
    async def test_create_ticket_online(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        mock_client = AsyncMock()
        mock_client.post_ticket = AsyncMock(return_value={"status": "ok", "ticket_id": "t_123"})
        mock_client.close = AsyncMock()

        with patch("src.api_client.CopilotAPIClient", return_value=mock_client):
            result = await async_ticket(
                api_url="http://test:8000",
                title="Online ticket",
                description="Should submit to API",
            )

        assert result["status"] == "ok"
        mock_client.post_ticket.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_title_cancels(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        result = await async_ticket(offline=True, title="", description="")
        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_auto_priority_applied(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        result = await async_ticket(
            offline=True,
            title="Production crash needs fix",
            description="Everything is down",
        )
        assert result["status"] == "queued"

        from src.local.jsonl_queue import JSONLQueue
        q = JSONLQueue(tmp_path / "tickets.jsonl")
        records = q.read_all()
        assert records[0]["priority"] == "urgent"
