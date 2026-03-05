"""Conversation history management."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Conversation

logger = logging.getLogger(__name__)


async def get_conversation_history(
    conversation_id: str,
    session: AsyncSession,
    max_messages: int = 20,
) -> list[dict[str, Any]]:
    """Retrieve conversation history by conversation_id."""
    stmt = select(Conversation).where(Conversation.conversation_id == conversation_id)
    result = await session.execute(stmt)
    conv = result.scalar_one_or_none()

    if conv is None:
        return []

    messages = conv.messages or []
    # Return the most recent messages up to max
    return messages[-max_messages:]


async def append_to_conversation(
    conversation_id: str,
    user_id: str,
    user_message: str,
    bot_response: str,
    session: AsyncSession,
) -> None:
    """Append a user/bot exchange to the conversation history."""
    stmt = select(Conversation).where(Conversation.conversation_id == conversation_id)
    result = await session.execute(stmt)
    conv = result.scalar_one_or_none()

    if conv is None:
        conv = Conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            messages=[],
        )
        session.add(conv)

    messages = list(conv.messages or [])
    messages.append({"role": "user", "content": user_message})
    messages.append({"role": "assistant", "content": bot_response})
    conv.messages = messages

    await session.flush()
