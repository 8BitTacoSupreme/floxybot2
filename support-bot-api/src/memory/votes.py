"""Vote and feedback recording with DB persistence and Kafka publishing."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from ..db.models import Feedback as FeedbackModel
from ..db.models import Vote as VoteModel

logger = logging.getLogger(__name__)

# Module-level event publisher (injected via set_publisher)
_publisher = None


def set_publisher(publisher) -> None:
    """Inject event publisher for vote/feedback events."""
    global _publisher
    _publisher = publisher


async def record_vote(
    vote_data: dict[str, Any],
    session=None,
    publisher=None,
) -> dict[str, Any]:
    """Record a user vote on a bot response.

    Validates, persists to DB, publishes to Kafka.
    """
    from src.schemas.vote import Vote

    try:
        vote = Vote(**vote_data)
    except Exception as e:
        logger.warning("Invalid vote data: %s", e)
        return {"status": "error", "detail": str(e)}

    # Persist to DB if session provided
    if session is not None:
        db_vote = VoteModel(
            id=vote.vote_id,
            message_id=vote.message_id,
            conversation_id=vote.conversation_id,
            user_id=vote.user_id,
            vote=vote.vote.value,
            query_text=vote_data.get("query_text"),
            response_text=vote_data.get("response_text"),
            skills_used=vote_data.get("skills_used", {}),
            comment=vote.comment,
        )
        session.add(db_vote)
        await session.flush()

    # Publish to Kafka
    pub = publisher or _publisher
    if pub is not None:
        try:
            await pub.publish(
                topic="floxbot.votes",
                key=vote.user_id,
                value={
                    "vote_id": str(vote.vote_id),
                    "message_id": str(vote.message_id),
                    "conversation_id": vote.conversation_id,
                    "user_id": vote.user_id,
                    "vote": vote.vote.value,
                    "timestamp": vote.timestamp.isoformat(),
                },
            )
        except Exception as e:
            logger.warning("Failed to publish vote event: %s", e)

    return {"status": "ok", "vote_id": str(vote.vote_id)}


async def record_feedback(
    feedback_data: dict[str, Any],
    session=None,
    publisher=None,
) -> dict[str, Any]:
    """Record structured user feedback.

    Validates, persists to DB, publishes to Kafka.
    """
    from src.schemas.vote import Feedback

    try:
        fb = Feedback(**feedback_data)
    except Exception as e:
        logger.warning("Invalid feedback data: %s", e)
        return {"status": "error", "detail": str(e)}

    # Persist to DB if session provided
    if session is not None:
        db_fb = FeedbackModel(
            id=fb.feedback_id,
            message_id=fb.message_id,
            conversation_id=fb.conversation_id,
            user_id=fb.user_id,
            category=fb.category.value,
            detail=fb.detail,
        )
        session.add(db_fb)
        await session.flush()

    # Publish to Kafka
    pub = publisher or _publisher
    if pub is not None:
        try:
            await pub.publish(
                topic="floxbot.feedback",
                key=fb.user_id,
                value={
                    "feedback_id": str(fb.feedback_id),
                    "message_id": str(fb.message_id),
                    "conversation_id": fb.conversation_id,
                    "user_id": fb.user_id,
                    "category": fb.category.value,
                    "detail": fb.detail,
                    "timestamp": fb.timestamp.isoformat(),
                },
            )
        except Exception as e:
            logger.warning("Failed to publish feedback event: %s", e)

    return {"status": "ok", "feedback_id": str(fb.feedback_id)}
