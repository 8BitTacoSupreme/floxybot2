"""Claude LLM backend — conversation, reasoning, teaching, orchestration."""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

import anthropic

from ..models.types import BuiltContext, SkillPackage
from .prompts import build_messages, build_system_prompt
from .tools import MCP_TOOLS, execute_tool

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

    # Call Anthropic API with tool-use support
    client = anthropic.AsyncAnthropic(api_key=settings.CLAUDE_API_KEY)
    max_tool_rounds = 3
    total_timeout = 45.0

    try:
        import time
        start_time = time.monotonic()

        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=MCP_TOOLS,
        )

        # Tool-use loop: if Claude requests a tool, execute and continue
        tool_round = 0
        while response.stop_reason == "tool_use" and tool_round < max_tool_rounds:
            elapsed = time.monotonic() - start_time
            if elapsed > total_timeout:
                logger.warning("Tool-use loop exceeded %.0fs timeout", total_timeout)
                break

            tool_round += 1

            # Append assistant's response (with tool_use blocks) to messages
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool_use block and build tool_result messages
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("Tool call %d: %s(%s)", tool_round, block.name, block.input)
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
                model=settings.CLAUDE_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=MCP_TOOLS,
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

    # Parse response — extract text blocks from the final response
    response_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            response_text += block.text
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
