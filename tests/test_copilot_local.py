"""Tests for Co-Pilot local storage: SQLite, ChromaDB, JSONL queues."""

from __future__ import annotations

import os
import tempfile

import pytest

from src.local.sqlite_store import SQLiteStore
from src.local.chroma_store import ChromaStore
from src.local.jsonl_queue import JSONLQueue


# --- SQLite Store ---

class TestSQLiteStore:
    @pytest.mark.asyncio
    async def test_init_creates_tables(self):
        store = SQLiteStore(":memory:")
        await store.init()
        count = await store.get_canon_chunk_count()
        assert count == 0
        await store.close()

    @pytest.mark.asyncio
    async def test_canon_chunk_upsert_and_query(self):
        store = SQLiteStore(":memory:")
        await store.init()
        await store.upsert_canon_chunk("c1", "core-canon", "Install", "Use flox install", "hash1")
        await store.upsert_canon_chunk("c2", "skill-k8s", "Deploy", "Use kubectl apply", "hash2")

        all_chunks = await store.get_canon_chunks()
        assert len(all_chunks) == 2

        k8s_chunks = await store.get_canon_chunks(skill_name="skill-k8s")
        assert len(k8s_chunks) == 1
        assert k8s_chunks[0]["content"] == "Use kubectl apply"

        assert await store.get_canon_chunk_count() == 2
        await store.close()

    @pytest.mark.asyncio
    async def test_canon_chunk_upsert_overwrites(self):
        store = SQLiteStore(":memory:")
        await store.init()
        await store.upsert_canon_chunk("c1", "core-canon", "Install", "v1", "hash1")
        await store.upsert_canon_chunk("c1", "core-canon", "Install", "v2", "hash2")
        chunks = await store.get_canon_chunks()
        assert len(chunks) == 1
        assert chunks[0]["content"] == "v2"
        await store.close()

    @pytest.mark.asyncio
    async def test_conversation_save_and_get(self):
        store = SQLiteStore(":memory:")
        await store.init()
        msgs = [{"role": "user", "content": "hello"}, {"role": "bot", "content": "hi"}]
        await store.save_conversation("conv_1", msgs)
        result = await store.get_conversation("conv_1")
        assert result == msgs
        assert await store.get_conversation("nonexistent") is None
        await store.close()

    @pytest.mark.asyncio
    async def test_user_memory_crud(self):
        store = SQLiteStore(":memory:")
        await store.init()
        assert await store.get_memory("skill_level") is None
        await store.set_memory("skill_level", "intermediate")
        assert await store.get_memory("skill_level") == "intermediate"

        await store.set_memory("projects", {"myproject": True})
        all_mem = await store.get_all_memory()
        assert "skill_level" in all_mem
        assert "projects" in all_mem
        await store.close()

    @pytest.mark.asyncio
    async def test_sync_metadata(self):
        store = SQLiteStore(":memory:")
        await store.init()
        assert await store.get_sync_meta("last_canon_sync") is None
        await store.set_sync_meta("last_canon_sync", "2026-03-01T00:00:00Z")
        assert await store.get_sync_meta("last_canon_sync") == "2026-03-01T00:00:00Z"
        await store.close()

    @pytest.mark.asyncio
    async def test_entitlements_cache(self):
        store = SQLiteStore(":memory:")
        await store.init()
        assert await store.get_cached_entitlements("user1") is None
        ent = {"tier": "pro", "copilot_modes": ["ask", "chat", "diagnose"]}
        await store.cache_entitlements("user1", ent)
        cached = await store.get_cached_entitlements("user1")
        assert cached == ent
        await store.close()


# --- ChromaDB Store ---

class TestChromaStore:
    def test_add_and_query(self, tmp_path):
        store = ChromaStore(persist_dir=str(tmp_path / "chroma1"))
        store.add_chunks(
            ids=["c1", "c2", "c3"],
            documents=[
                "How to install packages with flox",
                "Kubernetes deployment with flox",
                "Terraform infrastructure setup",
            ],
            metadatas=[
                {"skill": "core-canon"},
                {"skill": "skill-k8s"},
                {"skill": "skill-terraform"},
            ],
        )
        assert store.count() == 3

        results = store.query("install packages", top_k=2)
        assert len(results) == 2
        assert results[0]["id"] == "c1"  # best match

    def test_empty_query(self, tmp_path):
        store = ChromaStore(persist_dir=str(tmp_path / "chroma2"))
        results = store.query("anything")
        assert results == []

    def test_clear(self, tmp_path):
        store = ChromaStore(persist_dir=str(tmp_path / "chroma3"))
        store.add_chunks(ids=["c1"], documents=["test doc"])
        assert store.count() == 1
        store.clear()
        assert store.count() == 0

    def test_upsert_updates(self, tmp_path):
        store = ChromaStore(persist_dir=str(tmp_path / "chroma4"))
        store.add_chunks(ids=["c1"], documents=["version 1"])
        store.add_chunks(ids=["c1"], documents=["version 2"])
        assert store.count() == 1
        results = store.query("version", top_k=1)
        assert results[0]["document"] == "version 2"


# --- JSONL Queue ---

class TestJSONLQueue:
    def test_append_and_read(self, tmp_path):
        q = JSONLQueue(tmp_path / "test.jsonl")
        q.append({"type": "vote", "value": "up"})
        q.append({"type": "vote", "value": "down"})
        records = q.read_all()
        assert len(records) == 2
        assert records[0]["value"] == "up"

    def test_read_empty(self, tmp_path):
        q = JSONLQueue(tmp_path / "empty.jsonl")
        assert q.read_all() == []

    def test_count(self, tmp_path):
        q = JSONLQueue(tmp_path / "count.jsonl")
        assert q.count() == 0
        q.append({"a": 1})
        q.append({"b": 2})
        assert q.count() == 2

    @pytest.mark.asyncio
    async def test_flush(self, tmp_path):
        q = JSONLQueue(tmp_path / "flush.jsonl")
        q.append({"a": 1})
        q.append({"b": 2})

        received = []

        async def callback(records):
            received.extend(records)

        flushed = await q.flush(callback)
        assert flushed == 2
        assert len(received) == 2
        # After flush, queue is empty
        assert q.read_all() == []

    @pytest.mark.asyncio
    async def test_flush_empty(self, tmp_path):
        q = JSONLQueue(tmp_path / "empty_flush.jsonl")

        async def callback(records):
            raise AssertionError("Should not be called")

        flushed = await q.flush(callback)
        assert flushed == 0

    @pytest.mark.asyncio
    async def test_flush_callback_failure(self, tmp_path):
        q = JSONLQueue(tmp_path / "fail.jsonl")
        q.append({"a": 1})

        async def bad_callback(records):
            raise ConnectionError("API down")

        with pytest.raises(ConnectionError):
            await q.flush(bad_callback)
        # Records should still be there (flush was not completed)
        assert q.count() == 1
