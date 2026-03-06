"""Context engine — builds the full context for LLM calls."""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.types import BuiltContext, Entitlements

logger = logging.getLogger(__name__)


async def build_context(
    message: dict[str, Any],
    entitlements: Entitlements,
    session: AsyncSession | None = None,
) -> BuiltContext:
    """Build context from user memory, RAG results, project info, and conversation history.

    Pipeline:
    1. Extract project context from message
    2. Load user memory from DB (if entitled)
    3. Query RAG against canon
    4. Retrieve conversation history
    """
    context = BuiltContext()

    # Extract project context from message
    msg_context = message.get("context", {})
    if project := msg_context.get("project"):
        context.project_context = project

    text = message.get("content", {}).get("text", "")
    user_id = message.get("user_identity", {}).get("canonical_user_id")
    conversation_id = msg_context.get("conversation_id")

    # 1. User memory lookup (if entitled and session available)
    if entitlements.memory_enabled and user_id and session is not None:
        try:
            from ..memory.user import get_user_memory
            context.user_memory = await get_user_memory(user_id, session=session)
        except Exception as e:
            logger.warning("Failed to load user memory: %s", e)

    # 2. RAG query against canon
    if text and session is not None:
        try:
            from ..rag.engine import query_canon
            skill_filter = None
            if isinstance(context.project_context, dict):
                detected = context.project_context.get("detected_skills", [])
                if detected:
                    skill_filter = detected
            context.rag_results = await query_canon(
                text, session=session, skill_names=skill_filter
            )
        except Exception as e:
            logger.warning("RAG query failed: %s", e)

    # 2b. Instance knowledge (Tier 2) — upvoted Q&A pairs
    if text and session is not None:
        try:
            from ..rag.engine import query_instance_knowledge
            context.instance_knowledge = await query_instance_knowledge(
                text, session=session, top_k=3
            )
        except Exception as e:
            logger.warning("Instance knowledge query failed: %s", e)

    # 3. Conversation history retrieval
    if conversation_id and session is not None:
        try:
            from ..memory.conversations import get_conversation_history
            context.conversation_history = await get_conversation_history(
                conversation_id, session=session
            )
        except Exception as e:
            logger.warning("Failed to load conversation history: %s", e)

    return context
