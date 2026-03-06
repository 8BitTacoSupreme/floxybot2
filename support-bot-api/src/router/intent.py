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

# --------------------------------------------------------------------------
# Multi-signal intent scoring
# --------------------------------------------------------------------------

_CODE_SIGNALS = [
    "manifest", "hook", "service", "write", "generate", "create",
    "edit", "add to", "script", "toml",
]
_DIAGNOSTIC_SIGNALS = [
    "error", "debug", "failing", "broken", "not working", "diagnose",
    "logs", "crash", "exception", "traceback", "fix",
]
_TEACHING_SIGNALS = [
    "how", "explain", "teach", "learn", "why", "what is", "guide",
    "tutorial", "understand", "concept",
]
_ESCALATION_SIGNALS = [
    "billing", "account", "security", "refund", "cancel", "subscription",
    "payment", "invoice",
]


class IntentResult:
    """Intent classification with confidence score."""

    __slots__ = ("intent", "confidence", "scores")

    def __init__(self, intent: Intent, confidence: float, scores: dict[Intent, float]):
        self.intent = intent
        self.confidence = confidence
        self.scores = scores


async def classify_intent(
    message: dict[str, Any],
    context: BuiltContext,
    skills: list[SkillPackage],
) -> Intent:
    """Classify user intent using multi-signal confidence scoring.

    Scores each intent independently, picks the highest. If the top two
    are within 0.1, returns CONVERSATIONAL (Claude orchestrates both).
    Escalation signals override everything.
    """
    result = score_intent(message, context, skills)
    return result.intent


def score_intent(
    message: dict[str, Any],
    context: BuiltContext,
    skills: list[SkillPackage],
) -> IntentResult:
    """Score all intents and return the result with confidence."""
    text = message.get("content", {}).get("text", "").lower()
    code_blocks = message.get("content", {}).get("code_blocks", [])

    scores: dict[Intent, float] = {
        Intent.CONVERSATIONAL: 0.1,  # slight base so it wins on empty input
        Intent.CODE_GENERATION: 0.0,
        Intent.DIAGNOSTIC: 0.0,
        Intent.TEACHING: 0.0,
    }

    # --- Escalation override ---
    for signal in _ESCALATION_SIGNALS:
        if signal in text:
            # Return CONVERSATIONAL but with escalation metadata handled upstream
            return IntentResult(
                intent=Intent.CONVERSATIONAL,
                confidence=1.0,
                scores=scores,
            )

    # --- Code generation signals ---
    if code_blocks:
        scores[Intent.CODE_GENERATION] += 0.4
    for signal in _CODE_SIGNALS:
        if signal in text:
            scores[Intent.CODE_GENERATION] += 0.3
            break  # only count keyword group once

    # --- Diagnostic signals ---
    diag_hit = False
    for signal in _DIAGNOSTIC_SIGNALS:
        if signal in text:
            scores[Intent.DIAGNOSTIC] += 0.5
            diag_hit = True
            break

    # Code blocks + error keywords = strongly diagnostic
    if code_blocks and diag_hit:
        scores[Intent.DIAGNOSTIC] += 0.3

    # --- Teaching signals ---
    for signal in _TEACHING_SIGNALS:
        if signal in text:
            scores[Intent.TEACHING] += 0.5
            break

    # --- Conversational boost ---
    if "?" in text and not code_blocks:
        scores[Intent.CONVERSATIONAL] += 0.15

    # --- Pick winner ---
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_intent, top_score = ranked[0]
    runner_up_score = ranked[1][1]

    # Hybrid: if top two are very close, let Claude orchestrate
    if top_score > 0 and (top_score - runner_up_score) < 0.1:
        top_intent = Intent.CONVERSATIONAL

    return IntentResult(
        intent=top_intent,
        confidence=min(top_score, 1.0),
        scores=scores,
    )


async def route_to_backend(
    intent: Intent,
    message: dict[str, Any],
    context: BuiltContext,
    skills: list[SkillPackage],
    entitlements: Entitlements,
) -> dict[str, Any]:
    """Route to the appropriate LLM backend based on intent.

    CONVERSATIONAL → Claude
    CODE_GENERATION → Codex (if entitled, else Claude)
    DIAGNOSTIC → Claude orchestrates, delegates to Codex
    TEACHING → Claude co-pilot mode
    """
    backend = INTENT_BACKEND_MAP[intent]

    # Gate Codex access on entitlements
    if backend == LLMBackend.CODEX and not entitlements.codex_enabled:
        backend = LLMBackend.CLAUDE

    from ..llm.claude import call_claude
    from ..llm.codex import call_codex

    if backend == LLMBackend.CLAUDE:
        response = await call_claude(message, context, skills, intent=intent.value)
    else:
        response = await call_codex(message, context, skills, intent=intent.value)

    return response
