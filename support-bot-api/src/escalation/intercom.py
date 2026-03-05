"""Escalation to Intercom — auto-ticket with context bundle."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Escalation triggers:
# - Explicit user request
# - 3+ failed attempts on same topic
# - Confidence below threshold
# - Billing/account/security topics


async def should_escalate(
    message: dict[str, Any],
    context: dict[str, Any],
    confidence: float,
    escalation_attempts: int,
) -> bool:
    """Determine if the interaction should be escalated to human support."""
    text = message.get("content", {}).get("text", "").lower()

    # Explicit request
    if any(kw in text for kw in ["talk to human", "escalate", "support ticket", "speak to someone"]):
        return True

    # Too many failed attempts
    if escalation_attempts >= 3:
        return True

    # Low confidence
    if confidence < 0.3:
        return True

    # Sensitive topics
    if any(kw in text for kw in ["billing", "payment", "account", "security", "vulnerability"]):
        return True

    return False


async def create_ticket(
    message: dict[str, Any],
    context: dict[str, Any],
    entitlement_tier: str,
) -> dict[str, Any]:
    """Create an Intercom ticket with full context bundle.

    Entitled users get triaged tickets with full context.
    Community users get basic tickets.

    TODO: Implement Intercom API integration.
    """
    return {
        "status": "escalated",
        "ticket_id": None,
        "message": "Your request has been escalated to our support team.",
    }
