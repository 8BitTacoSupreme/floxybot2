"""Canon + memory + queue sync for the Co-Pilot."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def sync_canon():
    """Sync upstream canon to local SQLite + ChromaDB.

    TODO: Implement delta sync on activate or manual copilot-sync.
    """
    pass


async def sync_memory():
    """Sync user memory between local and Central API.

    TODO: Implement bidirectional sync.
    """
    pass


async def flush_queues():
    """Flush local JSONL queues (votes, feedback, tickets) to Central API.

    TODO: Implement queue drain on connectivity.
    """
    pass
