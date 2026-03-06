"""Async SQLite wrapper for Co-Pilot local storage.

Tables: canon_chunks, conversations, user_memory, sync_metadata, entitlements_cache
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS canon_chunks (
    id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    heading TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    content_hash TEXT UNIQUE NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    messages TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_memory (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entitlements_cache (
    user_id TEXT PRIMARY KEY,
    entitlements TEXT NOT NULL,
    cached_at TEXT NOT NULL
);
"""


class SQLiteStore:
    """Async SQLite wrapper for local Co-Pilot data."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Open connection and ensure schema."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # --- Canon chunks ---

    async def upsert_canon_chunk(
        self, chunk_id: str, skill_name: str, heading: str, content: str, content_hash: str
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT INTO canon_chunks (id, skill_name, heading, content, content_hash, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 content=excluded.content, content_hash=excluded.content_hash, updated_at=excluded.updated_at""",
            (chunk_id, skill_name, heading, content, content_hash, now),
        )
        await self._db.commit()

    async def get_canon_chunks(self, skill_name: str | None = None) -> list[dict[str, Any]]:
        if skill_name:
            cursor = await self._db.execute(
                "SELECT * FROM canon_chunks WHERE skill_name = ?", (skill_name,)
            )
        else:
            cursor = await self._db.execute("SELECT * FROM canon_chunks")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_canon_chunk_count(self) -> int:
        cursor = await self._db.execute("SELECT COUNT(*) FROM canon_chunks")
        row = await cursor.fetchone()
        return row[0]

    # --- Conversations ---

    async def save_conversation(self, conversation_id: str, messages: list[dict]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT INTO conversations (conversation_id, messages, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(conversation_id) DO UPDATE SET messages=excluded.messages, updated_at=excluded.updated_at""",
            (conversation_id, json.dumps(messages), now),
        )
        await self._db.commit()

    async def get_conversation(self, conversation_id: str) -> list[dict] | None:
        cursor = await self._db.execute(
            "SELECT messages FROM conversations WHERE conversation_id = ?", (conversation_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    # --- User memory ---

    async def set_memory(self, key: str, value: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT INTO user_memory (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (key, json.dumps(value), now),
        )
        await self._db.commit()

    async def get_memory(self, key: str) -> Any | None:
        cursor = await self._db.execute(
            "SELECT value FROM user_memory WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    async def get_all_memory(self) -> dict[str, Any]:
        cursor = await self._db.execute("SELECT key, value FROM user_memory")
        rows = await cursor.fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}

    # --- Sync metadata ---

    async def get_sync_meta(self, key: str) -> str | None:
        cursor = await self._db.execute(
            "SELECT value FROM sync_metadata WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def set_sync_meta(self, key: str, value: str) -> None:
        await self._db.execute(
            """INSERT INTO sync_metadata (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (key, value),
        )
        await self._db.commit()

    # --- Entitlements cache ---

    async def cache_entitlements(self, user_id: str, entitlements: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT INTO entitlements_cache (user_id, entitlements, cached_at) VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET entitlements=excluded.entitlements, cached_at=excluded.cached_at""",
            (user_id, json.dumps(entitlements), now),
        )
        await self._db.commit()

    async def get_cached_entitlements(self, user_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT entitlements FROM entitlements_cache WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row[0])
