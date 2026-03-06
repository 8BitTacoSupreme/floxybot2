"""End-to-end integration tests for Co-Pilot with mocked API."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.local.sqlite_store import SQLiteStore
from src.local.chroma_store import ChromaStore
from src.local.jsonl_queue import JSONLQueue


class TestEndToEndOnline:
    """Integration tests with mocked API (online path)."""

    @pytest.mark.asyncio
    async def test_ask_then_vote(self, tmp_path, monkeypatch):
        """ask mode → get response → vote → check JSONL queue."""
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        mock_client = AsyncMock()
        mock_client.post_message = AsyncMock(return_value={
            "text": "Use flox install python3",
            "message_id": "msg_001",
            "status": "ok",
        })
        mock_client.close = AsyncMock()

        with patch("src.api_client.CopilotAPIClient", return_value=mock_client):
            with patch("builtins.input", return_value="y"):
                from src.modes.ask import async_ask
                answer = await async_ask("install python", api_url="http://test:8000")

        assert "flox install" in answer
        # Vote should be queued
        q = JSONLQueue(tmp_path / "votes.jsonl")
        records = q.read_all()
        assert len(records) == 1
        assert records[0]["vote"] == "up"

    @pytest.mark.asyncio
    async def test_sync_then_offline_ask(self, tmp_path, monkeypatch):
        """Sync canon → go offline → ask should use local data."""
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        # Simulate sync
        sqlite = SQLiteStore(tmp_path / "copilot.db")
        await sqlite.init()
        await sqlite.upsert_canon_chunk(
            "c1", "core-canon", "Install", "Use flox install <pkg> to add packages", "hash1"
        )
        chroma = ChromaStore(persist_dir=str(tmp_path / "chroma"))
        chroma.add_chunks(
            ids=["c1"],
            documents=["Use flox install <pkg> to add packages"],
            metadatas=[{"skill_name": "core-canon", "heading": "Install"}],
        )
        await sqlite.close()

        # Now ask offline
        from src.modes.ask import async_ask
        answer = await async_ask("how do I install packages?", offline=True)
        assert "flox install" in answer.lower()

    @pytest.mark.asyncio
    async def test_entitlement_gating(self, tmp_path, monkeypatch):
        """Community tier can't access diagnose mode."""
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        from src.entitlements import check_mode_access
        community_ent = {"tier": "community", "copilot_modes": ["ask", "chat"]}

        allowed, reason = check_mode_access("diagnose", community_ent)
        assert allowed is False
        assert "Pro" in reason

        # Pro can access
        pro_ent = {"tier": "pro", "copilot_modes": ["ask", "chat", "diagnose", "learn", "feedback", "ticket"]}
        allowed, reason = check_mode_access("diagnose", pro_ent)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_feedback_then_sync(self, tmp_path, monkeypatch):
        """Submit feedback offline → sync flushes to API."""
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        # Submit feedback offline
        from src.modes.feedback import async_feedback
        result = await async_feedback(offline=True, category="helpful", detail="Great docs!")
        assert result["status"] == "ok"

        # Verify queued
        q = JSONLQueue(tmp_path / "feedback.jsonl")
        assert q.count() == 1

        # Sync should flush
        mock_client = AsyncMock()
        mock_client.get_canon_sync = AsyncMock(return_value=[])
        mock_client.get_memory = AsyncMock(return_value={})
        mock_client.put_memory = AsyncMock()
        mock_client.post_votes_batch = AsyncMock()
        mock_client.post_feedback = AsyncMock()
        mock_client.post_ticket = AsyncMock()

        from src.sync import flush_queues
        count = await flush_queues(mock_client, tmp_path)
        assert count == 1
        mock_client.post_feedback.assert_called_once()

        # Queue should be empty after flush
        assert q.count() == 0

    @pytest.mark.asyncio
    async def test_ticket_with_context_bundle(self, tmp_path, monkeypatch):
        """Ticket includes context bundle."""
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        # Create a flox env
        flox_dir = tmp_path / ".flox" / "env"
        flox_dir.mkdir(parents=True)
        (flox_dir / "manifest.toml").write_text('[install]\npython3.pkg-path = "python3"\n')

        from src.modes.ticket import async_ticket
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "python3"
            result = await async_ticket(
                offline=True,
                title="Need help with python setup",
                description="Can't get python working in my env",
            )

        assert result["status"] == "queued"
        q = JSONLQueue(tmp_path / "tickets.jsonl")
        records = q.read_all()
        assert len(records) == 1
        assert "manifest" in records[0]["context_bundle"]

    @pytest.mark.asyncio
    async def test_full_sync_flow(self, tmp_path, monkeypatch):
        """Full sync: canon + memory + queue flush."""
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        mock_client = AsyncMock()
        mock_client.get_canon_sync = AsyncMock(return_value=[
            {"id": "c1", "skill_name": "core-canon", "heading": "Basics", "content": "Flox intro", "content_hash": "h1"},
        ])
        mock_client.get_memory = AsyncMock(return_value={"skill_level": "intermediate"})
        mock_client.put_memory = AsyncMock()
        mock_client.post_votes_batch = AsyncMock()
        mock_client.post_feedback = AsyncMock()
        mock_client.post_ticket = AsyncMock()

        sqlite = SQLiteStore(tmp_path / "copilot.db")
        await sqlite.init()
        chroma = ChromaStore(persist_dir=str(tmp_path / "chroma"))

        from src.sync import run_sync
        results = await run_sync(mock_client, sqlite, chroma, tmp_path, "user1", timeout=10.0)

        assert results["canon"] == 1
        assert results["errors"] == []

        # Verify local stores populated
        assert await sqlite.get_canon_chunk_count() == 1
        assert chroma.count() == 1
        assert await sqlite.get_memory("skill_level") == "intermediate"

        await sqlite.close()


class TestEndToEndOffline:
    """Integration tests with no API (offline path)."""

    @pytest.mark.asyncio
    async def test_seeded_offline_ask(self, tmp_path, monkeypatch):
        """With seeded local data, ask works offline."""
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        # Seed local stores
        sqlite = SQLiteStore(tmp_path / "copilot.db")
        await sqlite.init()
        await sqlite.upsert_canon_chunk(
            "c1", "core-canon", "Environments",
            "Flox environments are reproducible dev shells", "hash1"
        )
        chroma = ChromaStore(persist_dir=str(tmp_path / "chroma"))
        chroma.add_chunks(
            ids=["c1"],
            documents=["Flox environments are reproducible dev shells"],
            metadatas=[{"skill_name": "core-canon"}],
        )
        await sqlite.close()

        from src.modes.ask import async_ask
        answer = await async_ask("what are flox environments?", offline=True)
        assert "reproducible" in answer.lower() or "flox" in answer.lower()

    @pytest.mark.asyncio
    async def test_entitlements_cache_offline(self, tmp_path, monkeypatch):
        """Cached entitlements survive offline."""
        monkeypatch.setenv("FLOXBOT_COPILOT_DATA_DIR", str(tmp_path))

        sqlite = SQLiteStore(tmp_path / "copilot.db")
        await sqlite.init()
        await sqlite.cache_entitlements("user1", {
            "tier": "pro",
            "copilot_modes": ["ask", "chat", "diagnose", "learn", "feedback", "ticket"],
        })

        from src.entitlements import resolve_local_entitlements
        offline_client = AsyncMock()
        offline_client.get_entitlements = AsyncMock(side_effect=ConnectionError("offline"))

        ent = await resolve_local_entitlements(offline_client, sqlite, "user1")
        assert ent["tier"] == "pro"
        await sqlite.close()
