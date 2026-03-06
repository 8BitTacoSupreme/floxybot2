"""Tests for Co-Pilot sync engine."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.local.sqlite_store import SQLiteStore
from src.local.chroma_store import ChromaStore
from src.sync import sync_canon, sync_memory, flush_queues, run_sync


@pytest.fixture
def mock_api_client():
    client = AsyncMock()
    client.get_canon_sync = AsyncMock(return_value=[])
    client.get_memory = AsyncMock(return_value={})
    client.put_memory = AsyncMock()
    client.post_votes_batch = AsyncMock()
    client.post_feedback = AsyncMock()
    client.post_ticket = AsyncMock()
    return client


class TestSyncCanon:
    @pytest.mark.asyncio
    async def test_no_new_chunks(self, mock_api_client, tmp_path):
        store = SQLiteStore(":memory:")
        await store.init()
        chroma = ChromaStore(persist_dir=str(tmp_path / "chroma"))

        count = await sync_canon(mock_api_client, store, chroma)
        assert count == 0

    @pytest.mark.asyncio
    async def test_delta_sync(self, mock_api_client, tmp_path):
        mock_api_client.get_canon_sync.return_value = [
            {"id": "c1", "skill_name": "core-canon", "heading": "Install", "content": "Use flox install", "content_hash": "h1"},
            {"id": "c2", "skill_name": "skill-k8s", "heading": "Deploy", "content": "kubectl apply", "content_hash": "h2"},
        ]
        store = SQLiteStore(":memory:")
        await store.init()
        chroma = ChromaStore(persist_dir=str(tmp_path / "chroma"))

        count = await sync_canon(mock_api_client, store, chroma)
        assert count == 2
        assert await store.get_canon_chunk_count() == 2
        assert chroma.count() == 2

        # Verify sync metadata updated
        last_sync = await store.get_sync_meta("last_canon_sync")
        assert last_sync is not None


class TestSyncMemory:
    @pytest.mark.asyncio
    async def test_empty_remote(self, mock_api_client):
        store = SQLiteStore(":memory:")
        await store.init()

        result = await sync_memory(mock_api_client, store, "user1")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_remote_overwrites_local(self, mock_api_client):
        mock_api_client.get_memory.return_value = {"skill_level": "expert"}
        store = SQLiteStore(":memory:")
        await store.init()
        await store.set_memory("skill_level", "beginner")

        result = await sync_memory(mock_api_client, store, "user1")
        assert result["skill_level"] == "expert"

    @pytest.mark.asyncio
    async def test_local_pushes_to_remote(self, mock_api_client):
        mock_api_client.get_memory.return_value = {}
        store = SQLiteStore(":memory:")
        await store.init()
        await store.set_memory("local_pref", "dark_mode")

        await sync_memory(mock_api_client, store, "user1")
        mock_api_client.put_memory.assert_called_once()


class TestFlushQueues:
    @pytest.mark.asyncio
    async def test_empty_queues(self, mock_api_client, tmp_path):
        count = await flush_queues(mock_api_client, tmp_path)
        assert count == 0

    @pytest.mark.asyncio
    async def test_flush_votes(self, mock_api_client, tmp_path):
        from src.local.jsonl_queue import JSONLQueue
        q = JSONLQueue(tmp_path / "votes.jsonl")
        q.append({"vote": "up"})
        q.append({"vote": "down"})

        count = await flush_queues(mock_api_client, tmp_path)
        assert count == 2
        mock_api_client.post_votes_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_partial_failure(self, mock_api_client, tmp_path):
        """If votes flush fails, feedback and tickets still attempt."""
        from src.local.jsonl_queue import JSONLQueue
        JSONLQueue(tmp_path / "votes.jsonl").append({"vote": "up"})
        JSONLQueue(tmp_path / "feedback.jsonl").append({"detail": "great"})

        mock_api_client.post_votes_batch.side_effect = ConnectionError("API down")

        count = await flush_queues(mock_api_client, tmp_path)
        # Feedback flushed (1), votes failed (0)
        assert count == 1


class TestRunSync:
    @pytest.mark.asyncio
    async def test_full_sync(self, mock_api_client, tmp_path):
        store = SQLiteStore(":memory:")
        await store.init()
        chroma = ChromaStore(persist_dir=str(tmp_path / "chroma"))

        results = await run_sync(mock_api_client, store, chroma, tmp_path, "user1", timeout=5.0)
        assert results["errors"] == []

    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path):
        """Sync times out gracefully."""
        import asyncio

        async def slow_canon(*args, **kwargs):
            await asyncio.sleep(10)
            return []

        client = AsyncMock()
        client.get_canon_sync = slow_canon
        client.get_memory = AsyncMock(return_value={})
        client.put_memory = AsyncMock()

        store = SQLiteStore(":memory:")
        await store.init()
        chroma = ChromaStore(persist_dir=str(tmp_path / "chroma"))

        results = await run_sync(client, store, chroma, tmp_path, "user1", timeout=0.1)
        assert any("timed out" in e for e in results["errors"])
