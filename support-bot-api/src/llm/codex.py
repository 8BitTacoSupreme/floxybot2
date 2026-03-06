"""Codex LLM backend — code generation, manifest editing, debugging.

Uses the same Anthropic API as Claude but with a code-focused system prompt
and scoring tuned for code quality signals.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from uuid import uuid4

import anthropic

from ..models.types import BuiltContext, SkillPackage
from .prompts import build_messages, build_system_prompt
from .tools import MCP_TOOLS, execute_tool

logger = logging.getLogger(__name__)


async def call_codex(
    message: dict[str, Any],
    context: BuiltContext,
    skills: list[SkillPackage],
    intent: str = "code_generation",
) -> dict[str, Any]:
    """Call Codex via the Anthropic API with a code-focused system prompt.

    Mirrors claude.py structure but uses CODEX_SYSTEM_PROMPT and
    code-oriented confidence scoring.
    """
    from src.config import settings

    text = message.get("content", {}).get("text", "")
    code_blocks = message.get("content", {}).get("code_blocks", [])

    # Build code-focused system prompt
    system_prompt = build_system_prompt(context, skills, intent, backend="codex")

    # Build message history
    history = context.conversation_history if context.conversation_history else []
    messages = build_messages(text, code_blocks, history)

    # Use Codex API key/model, fall back to Claude's if not set
    api_key = settings.CODEX_API_KEY or settings.CLAUDE_API_KEY
    model = settings.CODEX_MODEL or settings.CLAUDE_MODEL

    client = anthropic.AsyncAnthropic(api_key=api_key)
    max_tool_rounds = 3
    total_timeout = 45.0

    try:
        start_time = time.monotonic()

        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=MCP_TOOLS,
        )

        # Tool-use loop
        tool_round = 0
        while response.stop_reason == "tool_use" and tool_round < max_tool_rounds:
            elapsed = time.monotonic() - start_time
            if elapsed > total_timeout:
                logger.warning("Codex tool-use loop exceeded %.0fs timeout", total_timeout)
                break

            tool_round += 1

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("Codex tool call %d: %s(%s)", tool_round, block.name, block.input)
                    result_str = await execute_tool(
                        block.name, block.input, timeout=settings.MCP_TOOL_TIMEOUT
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            messages.append({"role": "user", "content": tool_results})

            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=MCP_TOOLS,
            )

    except anthropic.APIError as e:
        logger.error("Codex API error: %s", e)
        return {
            "response_id": str(uuid4()),
            "message_id": message.get("message_id", str(uuid4())),
            "status": "error",
            "text": "I'm having trouble connecting to the code generation backend. Please try again.",
            "code_blocks": [],
            "skills_used": [],
            "confidence": 0.0,
            "llm_backend": "codex",
            "suggested_votes": False,
        }

    # Parse response
    response_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            response_text += block.text

    extracted_code = extract_code_blocks(response_text)
    confidence = estimate_code_confidence(response_text, context, extracted_code)

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
        "llm_backend": "codex",
        "suggested_votes": True,
    }


def extract_code_blocks(text: str) -> list[str]:
    """Extract fenced code blocks with language detection."""
    pattern = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
    return [match.group(2).strip() for match in pattern.finditer(text)]


def estimate_code_confidence(
    response_text: str,
    context: BuiltContext,
    code_blocks: list[str],
) -> float:
    """Estimate confidence weighted toward code quality signals."""
    score = 0.4  # lower base than conversational

    # Strong boost for actual code output
    if code_blocks:
        score += 0.3

    # Boost if RAG results backed the response
    if context.rag_results:
        score += 0.15

    # Boost if skills were loaded
    if context.skills:
        score += 0.1

    # Reduce for hedging
    hedging = ["i'm not sure", "might not work", "untested", "you may need to adjust"]
    text_lower = response_text.lower()
    for phrase in hedging:
        if phrase in text_lower:
            score -= 0.1
            break

    return max(0.0, min(1.0, score))
