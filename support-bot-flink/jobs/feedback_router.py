"""Feedback routing consumer.

Consumes ``floxbot.feedback`` and routes by category:
- incorrect/outdated → doc_gap (canon forge queue)
- incomplete → skill_improvement
- confusing → pattern_suggestion
- helpful → positive_signal (instance knowledge weight boost)
- other/unknown → triage_queue (human review)
"""

from __future__ import annotations

import logging
from typing import Any

from consumer_base import StreamConsumer

logger = logging.getLogger(__name__)

# Category → route mapping
CATEGORY_ROUTES = {
    "incorrect": "doc_gap",
    "outdated": "doc_gap",
    "incomplete": "skill_improvement",
    "confusing": "pattern_suggestion",
    "helpful": "positive_signal",
}
DEFAULT_ROUTE = "triage_queue"


class FeedbackRouterConsumer(StreamConsumer):
    """Routes feedback events by category."""

    def __init__(self):
        super().__init__(topics=["floxbot.feedback"], group_id="feedback-router")

    def process_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        category = event.get("category", "other").lower()
        route = CATEGORY_ROUTES.get(category, DEFAULT_ROUTE)

        routed = {
            "type": "feedback_routed",
            "route": route,
            "category": category,
            "user_id": event.get("user_id", "unknown"),
            "message_id": event.get("message_id", ""),
            "feedback_text": event.get("text", ""),
            "skill": event.get("skill", ""),
        }

        logger.info(
            "Feedback routed: category=%s → route=%s (user=%s)",
            category, route, routed["user_id"],
        )
        return [routed]

    def flush(self) -> list[dict[str, Any]]:
        return []
