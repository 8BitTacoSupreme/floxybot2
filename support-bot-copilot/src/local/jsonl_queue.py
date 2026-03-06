"""Append-only JSONL queue with file locking for offline queuing."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class JSONLQueue:
    """Append-only JSONL queue with file locking.

    Used for offline queuing of votes, feedback, and tickets.
    """

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        """Append a JSON record to the queue file."""
        with open(self.file_path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(record, default=str) + "\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def read_all(self) -> list[dict[str, Any]]:
        """Read all records from the queue file."""
        if not self.file_path.exists():
            return []

        records = []
        with open(self.file_path, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            logger.warning("Skipping malformed JSONL line")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return records

    async def flush(self, callback: Callable) -> int:
        """Read all records, send via callback, then truncate.

        The callback receives the list of records and should raise on failure.
        Returns the number of records flushed.
        """
        records = self.read_all()
        if not records:
            return 0

        await callback(records)

        # Atomic truncate: write empty to temp, rename over original
        tmp_path = self.file_path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            pass
        os.replace(tmp_path, self.file_path)

        return len(records)

    def count(self) -> int:
        """Return the number of records in the queue."""
        return len(self.read_all())
