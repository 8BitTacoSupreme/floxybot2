"""Intent classification and LLM routing."""

from __future__ import annotations

import logging
from typing import Any

from ..models.types import (
    BuiltContext,
    Entitlements,
    Intent,
    INTENT_BACKEND_MAP,
    LLMBackend,
    SkillPackage,
)

logger = logging.getLogger(__name__)


async def classify_intent(
    message: dict[str, Any],
    context: BuiltContext,
    skills: list[SkillPackage],
) -> Intent:
    """Classify user intent to determine LLM routing.

    TODO: Implement intent classification using lightweight model or heuristics.
    Signals: message content, code blocks present, question patterns,
    active skills, conversation history.
    """
    text = message.get("content", {}).get("text", "").lower()
    code_blocks = message.get("content", {}).get("code_blocks", [])

    # Simple heuristic classification — will be replaced with model-based
    if code_blocks or any(kw in text for kw in ["generate", "write code", "create a", "manifest"]):
        return Intent.CODE_GENERATION

    if any(kw in text for kw in ["debug", "error", "failing", "broken", "not working", "diagnose"]):
        return Intent.DIAGNOSTIC

    if any(kw in text for kw in ["how do i", "explain", "teach", "learn", "tutorial", "guide"]):
        return Intent.TEACHING

    return Intent.CONVERSATIONAL


async def route_to_backend(
    intent: Intent,
    message: dict[str, Any],
    context: BuiltContext,
    skills: list[SkillPackage],
    entitlements: Entitlements,
) -> dict[str, Any]:
    """Route to the appropriate LLM backend based on intent.

    CONVERSATIONAL → Claude
    CODE_GENERATION → Codex
    DIAGNOSTIC → Claude orchestrates, delegates to Codex
    TEACHING → Claude co-pilot mode
    """
    backend = INTENT_BACKEND_MAP[intent]

    # Gate Codex access on entitlements
    if backend == LLMBackend.CODEX and not entitlements.codex_enabled:
        backend = LLMBackend.CLAUDE

    # TODO: Call actual LLM backend
    from ..llm.claude import call_claude
    from ..llm.codex import call_codex

    if backend == LLMBackend.CLAUDE:
        response = await call_claude(message, context, skills)
    else:
        response = await call_codex(message, context, skills)

    return response
