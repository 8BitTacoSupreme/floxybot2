"""Canon + memory + queue sync for the Co-Pilot."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def sync_canon(api_client, sqlite_store, chroma_store):
    """Sync upstream canon to local SQLite + ChromaDB.

    Delta sync: fetches only chunks updated since last sync.
    """
    last_sync = await sqlite_store.get_sync_meta("last_canon_sync")
    since = last_sync or "2000-01-01T00:00:00Z"

    chunks = await api_client.get_canon_sync(since=since)
    if not chunks:
        logger.debug("Canon sync: no new chunks")
        return 0

    chroma_ids = []
    chroma_docs = []
    chroma_metas = []

    for chunk in chunks:
        await sqlite_store.upsert_canon_chunk(
            chunk_id=chunk["id"],
            skill_name=chunk.get("skill_name", ""),
            heading=chunk.get("heading", ""),
            content=chunk["content"],
            content_hash=chunk.get("content_hash", ""),
        )
        chroma_ids.append(chunk["id"])
        chroma_docs.append(chunk["content"])
        chroma_metas.append({"skill_name": chunk.get("skill_name", ""), "heading": chunk.get("heading", "")})

    if chroma_ids:
        chroma_store.add_chunks(ids=chroma_ids, documents=chroma_docs, metadatas=chroma_metas)

    now = datetime.now(timezone.utc).isoformat()
    await sqlite_store.set_sync_meta("last_canon_sync", now)

    logger.info("Canon sync: %d chunks synced", len(chunks))
    return len(chunks)


async def sync_memory(api_client, sqlite_store, user_id: str):
    """Sync user memory between local and Central API.

    Bidirectional merge with last-write-wins per field.
    """
    # Fetch remote memory
    remote_memory = await api_client.get_memory(user_id)
    local_memory = await sqlite_store.get_all_memory()

    # Merge: remote wins for fields present in remote
    merged = dict(local_memory)
    if remote_memory:
        for key, value in remote_memory.items():
            if value is not None and value != {} and value != []:
                merged[key] = value
                await sqlite_store.set_memory(key, value)

    # Push local-only fields to remote
    local_updates = {}
    for key, value in local_memory.items():
        if key not in remote_memory or remote_memory.get(key) in (None, {}, []):
            local_updates[key] = value

    if local_updates:
        await api_client.put_memory(user_id, local_updates)

    logger.info("Memory sync: %d fields merged", len(merged))
    return merged


async def flush_queues(api_client, data_dir):
    """Flush local JSONL queues (votes, feedback, tickets) to Central API."""
    from .local.jsonl_queue import JSONLQueue

    total_flushed = 0

    # Votes
    votes_queue = JSONLQueue(data_dir / "votes.jsonl")
    try:
        count = await votes_queue.flush(
            lambda records: api_client.post_votes_batch(records)
        )
        total_flushed += count
        if count:
            logger.info("Flushed %d votes", count)
    except Exception as e:
        logger.warning("Failed to flush votes: %s", e)

    # Feedback
    feedback_queue = JSONLQueue(data_dir / "feedback.jsonl")
    try:
        count = await feedback_queue.flush(
            lambda records: _post_feedback_batch(api_client, records)
        )
        total_flushed += count
        if count:
            logger.info("Flushed %d feedback records", count)
    except Exception as e:
        logger.warning("Failed to flush feedback: %s", e)

    # Tickets
    tickets_queue = JSONLQueue(data_dir / "tickets.jsonl")
    try:
        count = await tickets_queue.flush(
            lambda records: _post_tickets_batch(api_client, records)
        )
        total_flushed += count
        if count:
            logger.info("Flushed %d tickets", count)
    except Exception as e:
        logger.warning("Failed to flush tickets: %s", e)

    # Telemetry
    total_flushed += await flush_telemetry(api_client, data_dir)

    return total_flushed


async def flush_telemetry(api_client, data_dir):
    """Flush local telemetry JSONL queue to Central API."""
    from .local.jsonl_queue import JSONLQueue

    queue = JSONLQueue(data_dir / "telemetry.jsonl")
    try:
        count = await queue.flush(
            lambda records: api_client.post_telemetry(records)
        )
        if count:
            logger.info("Flushed %d telemetry records", count)
        return count
    except Exception as e:
        logger.warning("Failed to flush telemetry: %s", e)
        return 0


async def _post_feedback_batch(api_client, records):
    """Post feedback records one at a time (no batch endpoint)."""
    for record in records:
        await api_client.post_feedback(record)


async def _post_tickets_batch(api_client, records):
    """Post ticket records one at a time."""
    for record in records:
        await api_client.post_ticket(record)


async def run_sync(api_client, sqlite_store, chroma_store, data_dir, user_id: str, timeout: float = 2.0):
    """Run all sync operations with a timeout.

    Best-effort: catches TimeoutError and individual failures gracefully.
    """
    results = {"canon": 0, "memory": {}, "queues": 0, "errors": []}

    try:
        async with asyncio.timeout(timeout):
            try:
                results["canon"] = await sync_canon(api_client, sqlite_store, chroma_store)
            except Exception as e:
                results["errors"].append(f"canon: {e}")
                logger.warning("Canon sync failed: %s", e)

            try:
                results["memory"] = await sync_memory(api_client, sqlite_store, user_id)
            except Exception as e:
                results["errors"].append(f"memory: {e}")
                logger.warning("Memory sync failed: %s", e)

            try:
                results["queues"] = await flush_queues(api_client, data_dir)
            except Exception as e:
                results["errors"].append(f"queues: {e}")
                logger.warning("Queue flush failed: %s", e)

    except TimeoutError:
        results["errors"].append("sync timed out")
        logger.warning("Sync timed out after %.1fs", timeout)

    return results
