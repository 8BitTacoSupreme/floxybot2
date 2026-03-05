"""Claude LLM backend — conversation, reasoning, teaching, orchestration."""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

import anthropic

from ..models.types import BuiltContext, SkillPackage
from .prompts import build_messages, build_system_prompt

logger = logging.getLogger(__name__)


async def call_claude(
    message: dict[str, Any],
    context: BuiltContext,
    skills: list[SkillPackage],
    intent: str = "conversational",
) -> dict[str, Any]:
    """Call Claude via the Anthropic API.

    Assembles system prompt + messages, calls the API, parses the response.
    """
    from src.config import settings

    text = message.get("content", {}).get("text", "")
    code_blocks = message.get("content", {}).get("code_blocks", [])

    # Build system prompt with skills, RAG, user memory
    system_prompt = build_system_prompt(context, skills, intent)

    # Build message history
    history = context.conversation_history if context.conversation_history else []
    messages = build_messages(text, code_blocks, history)

    # Call Anthropic API
    client = anthropic.AsyncAnthropic(api_key=settings.CLAUDE_API_KEY)
    try:
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
        )
    except anthropic.APIError as e:
        logger.error("Claude API error: %s", e)
        return {
            "response_id": str(uuid4()),
            "message_id": message.get("message_id", str(uuid4())),
            "status": "error",
            "text": "I'm having trouble connecting to my language model. Please try again.",
            "code_blocks": [],
            "skills_used": [],
            "confidence": 0.0,
            "llm_backend": "claude",
            "suggested_votes": False,
        }

    # Parse response
    response_text = response.content[0].text if response.content else ""
    extracted_code = extract_code_blocks(response_text)
    confidence = estimate_confidence(response_text, context)

    return {
        "response_id": str(uuid4()),
        "message_id": message.get("message_id", str(uuid4())),
        "status": "ok",
        "text": response_text,
        "code_blocks": extracted_code,
        "skills_used": [
            {"name": s.name, "role": s.role, "tokens_used": s.token_budget}
            for s in skills
        ],
        "confidence": confidence,
        "llm_backend": "claude",
        "suggested_votes": True,
    }


def extract_code_blocks(text: str) -> list[str]:
    """Extract fenced code blocks from markdown response."""
    pattern = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)
    return pattern.findall(text)


def estimate_confidence(response_text: str, context: BuiltContext) -> float:
    """Estimate response confidence based on available context.

    Higher with RAG results, lower with hedging language.
    """
    score = 0.5  # base

    # Boost if RAG results were available
    if context.rag_results:
        score += 0.2 * min(len(context.rag_results), 3) / 3

    # Boost if skills were loaded
    if context.skills:
        score += 0.1

    # Reduce for hedging language
    hedging_phrases = [
        "i'm not sure", "i think", "might be", "possibly",
        "i don't know", "uncertain", "may not be accurate",
    ]
    text_lower = response_text.lower()
    for phrase in hedging_phrases:
        if phrase in text_lower:
            score -= 0.15
            break

    return max(0.0, min(1.0, score))
