"""Ticket creation, DB persistence, and Kafka publishing."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Ticket

logger = logging.getLogger(__name__)


async def create_ticket(
    ticket_data: dict[str, Any],
    session: AsyncSession | None = None,
    publisher=None,
) -> dict[str, Any]:
    """Create a triaged support ticket.

    Persists to DB and publishes to Kafka escalations topic.
    """
    ticket_id = uuid.uuid4()
    user_id = ticket_data.get("user_id", "anonymous")
    title = ticket_data.get("title", "Support Request")
    context_bundle = ticket_data.get("context_bundle", {})
    priority = ticket_data.get("priority", "normal")
    now = datetime.now(timezone.utc)

    # Persist to DB
    if session is not None:
        db_ticket = Ticket(
            id=ticket_id,
            user_id=user_id,
            title=title,
            context_bundle=context_bundle,
            priority=priority,
            status="open",
            created_at=now,
        )
        session.add(db_ticket)
        await session.flush()

    # Publish to Kafka
    if publisher is not None:
        try:
            await publisher.publish(
                topic="floxbot.escalations",
                key=user_id,
                value={
                    "ticket_id": str(ticket_id),
                    "user_id": user_id,
                    "title": title,
                    "priority": priority,
                    "status": "open",
                    "created_at": now.isoformat(),
                },
            )
        except Exception as e:
            logger.warning("Failed to publish ticket event: %s", e)

    return {
        "status": "ok",
        "ticket_id": str(ticket_id),
        "title": title,
        "priority": priority,
    }
