"""Co-Pilot ticket mode — bot-triaged support ticket (Pro/Enterprise)."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PRIORITY_LEVELS = ["low", "normal", "high", "urgent"]


def run(args):
    """Run ticket mode (sync entry point)."""
    asyncio.run(async_ticket(
        api_url=args.api_url,
        offline=getattr(args, "offline", False),
    ))


async def async_ticket(
    api_url: str = "http://localhost:8000",
    offline: bool = False,
    title: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a triaged support ticket with full context bundle."""
    from ..local.config import get_data_dir, is_offline
    from ..local.sqlite_store import SQLiteStore
    from ..local.jsonl_queue import JSONLQueue

    data_dir = get_data_dir()
    force_offline = offline or is_offline()

    # Interactive input if not provided
    if title is None:
        try:
            title = input("Ticket title: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("Cancelled.")
            return {"status": "cancelled"}

    if not title:
        print("No title provided, cancelled.")
        return {"status": "cancelled"}

    if description is None:
        try:
            description = input("Description: ").strip()
        except (EOFError, KeyboardInterrupt):
            description = ""

    # Auto-detect priority
    priority = _auto_priority(title, description)
    print(f"Auto-priority: {priority}")

    # Gather context bundle
    context_bundle = _gather_context_bundle(data_dir)

    ticket = {
        "ticket_id": str(uuid.uuid4()),
        "user_id": "",
        "title": title,
        "description": description,
        "priority": priority,
        "context_bundle": context_bundle,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Queue locally
    queue = JSONLQueue(data_dir / "tickets.jsonl")
    queue.append(ticket)
    print("Ticket queued locally.")

    # Try to submit immediately if online
    if not force_offline:
        try:
            from ..api_client import CopilotAPIClient
            client = CopilotAPIClient(api_url=api_url)
            result = await client.post_ticket(ticket)
            await client.close()
            print(f"Ticket submitted: {result.get('ticket_id', 'unknown')}")
            return {"status": "ok", "ticket_id": result.get("ticket_id")}
        except Exception as e:
            logger.warning("Could not submit ticket online: %s", e)
            print("Will sync when online.")

    return {"status": "queued", "ticket_id": ticket["ticket_id"]}


def _auto_priority(title: str, description: str) -> str:
    """Auto-classify priority based on keywords."""
    text = f"{title} {description}".lower()

    urgent_keywords = ["crash", "data loss", "security", "production down", "critical"]
    high_keywords = ["broken", "error", "failing", "cannot", "blocked"]
    low_keywords = ["question", "suggestion", "nice to have", "minor"]

    for kw in urgent_keywords:
        if kw in text:
            return "urgent"
    for kw in high_keywords:
        if kw in text:
            return "high"
    for kw in low_keywords:
        if kw in text:
            return "low"
    return "normal"


def _gather_context_bundle(data_dir: Path) -> dict[str, Any]:
    """Gather environment context for the ticket."""
    bundle: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Manifest
    manifest_path = Path.cwd() / ".flox" / "env" / "manifest.toml"
    if manifest_path.exists():
        bundle["manifest"] = manifest_path.read_text()

    # Flox status
    try:
        result = subprocess.run(
            ["flox", "status"], capture_output=True, text=True, timeout=10
        )
        bundle["flox_status"] = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        bundle["flox_status"] = "(unavailable)"

    # Recent conversation history
    try:
        from ..local.sqlite_store import SQLiteStore
        # Can't do async here easily, skip for now
        bundle["conversation_history"] = "(see local DB)"
    except Exception:
        pass

    return bundle
