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

    Entitled users (pro/enterprise) get triaged tickets with full context.
    Community users get basic tickets.

    Graceful fallback: no API key → log warning, return stub response.
    """
    from src.config import settings
    from src.events.sanitizer import sanitize_context

    api_key = settings.INTERCOM_API_KEY
    api_url = settings.INTERCOM_API_URL

    if not api_key:
        logger.warning("No Intercom API key configured — returning stub response")
        return {
            "status": "escalated",
            "ticket_id": None,
            "message": "Your request has been escalated to our support team.",
        }

    # Build the ticket body
    user_text = message.get("content", {}).get("text", "")
    user_email = message.get("user_identity", {}).get("email", "")
    user_id = message.get("user_identity", {}).get("canonical_user_id", "unknown")

    body: dict[str, Any] = {
        "message_type": "inapp",
        "body": f"Support escalation from FloxBot\n\nUser message: {user_text[:500]}",
    }

    if user_email:
        body["from"] = {"type": "user", "email": user_email}
    else:
        body["from"] = {"type": "user", "id": user_id}

    # Pro/Enterprise: attach full sanitized context
    if entitlement_tier in ("pro", "enterprise"):
        sanitized = sanitize_context(context)
        body["body"] += f"\n\n--- Context ---\nTier: {entitlement_tier}\n"
        skills = sanitized.get("project", {}).get("detected_skills", [])
        if skills:
            body["body"] += f"Skills: {', '.join(skills)}\n"
        conversation_id = sanitized.get("conversation_id", "")
        if conversation_id:
            body["body"] += f"Conversation: {conversation_id}\n"

    try:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{api_url}/conversations",
                json=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            ticket_id = data.get("conversation_id") or data.get("id")
            return {
                "status": "escalated",
                "ticket_id": ticket_id,
                "message": "Your request has been escalated to our support team.",
            }
    except Exception as e:
        logger.error("Intercom API error: %s", e)
        return {
            "status": "escalated",
            "ticket_id": None,
            "message": "Your request has been escalated to our support team.",
        }
