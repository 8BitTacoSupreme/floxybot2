"""Co-Pilot feedback mode — structured field intelligence (Pro/Enterprise)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

FEEDBACK_CATEGORIES = ["incorrect", "incomplete", "outdated", "confusing", "helpful", "other"]


def run(args):
    """Run feedback mode (sync entry point)."""
    asyncio.run(async_feedback(
        api_url=args.api_url,
        offline=getattr(args, "offline", False),
    ))


async def async_feedback(
    api_url: str = "http://localhost:8000",
    offline: bool = False,
    category: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """Collect structured feedback interactively."""
    from ..local.config import get_data_dir, is_offline
    from ..local.jsonl_queue import JSONLQueue

    data_dir = get_data_dir()
    force_offline = offline or is_offline()

    # Interactive input if not provided
    if not category:
        print("Feedback categories:")
        for i, cat in enumerate(FEEDBACK_CATEGORIES, 1):
            print(f"  {i}. {cat}")
        try:
            choice = input("Select category (1-6): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(FEEDBACK_CATEGORIES):
                category = FEEDBACK_CATEGORIES[idx]
            else:
                category = "other"
        except (ValueError, EOFError, KeyboardInterrupt):
            print("Cancelled.")
            return {"status": "cancelled"}

    if detail is None:
        try:
            detail = input("Detail: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("Cancelled.")
            return {"status": "cancelled"}

    if not detail:
        print("No detail provided, cancelled.")
        return {"status": "cancelled"}

    feedback = {
        "feedback_id": str(uuid.uuid4()),
        "message_id": str(uuid.uuid4()),
        "conversation_id": "",
        "user_id": "",
        "category": category,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Queue locally
    queue = JSONLQueue(data_dir / "feedback.jsonl")
    queue.append(feedback)
    print("Feedback recorded locally.")

    # Try to flush immediately if online
    if not force_offline:
        try:
            from ..api_client import CopilotAPIClient
            client = CopilotAPIClient(api_url=api_url)
            await client.post_feedback(feedback)
            await client.close()
            print("Feedback submitted to server.")
        except Exception as e:
            logger.warning("Could not submit feedback online: %s", e)
            print("Will sync when online.")

    return {"status": "ok", "feedback_id": feedback["feedback_id"]}
