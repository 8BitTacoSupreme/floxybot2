"""System prompt assembly for Claude LLM calls."""

from __future__ import annotations

from typing import Any

from ..models.types import BuiltContext, SkillPackage

SYSTEM_PROMPT_BASE = """You are FloxBot, an expert support assistant for Flox — the universal package manager and environment management tool. You help users with:

- Installing and managing packages with Flox
- Writing and editing manifest.toml files
- Configuring Flox environments, services, and hooks
- Debugging environment issues
- Understanding Flox concepts and workflows

Guidelines:
- Be concise and helpful. Prefer actionable answers over lengthy explanations.
- When showing commands, use code blocks with the appropriate shell syntax.
- When editing manifests, show the complete relevant section of manifest.toml.
- If you're unsure about something, say so rather than guessing.
- Reference official Flox documentation when relevant.
- If the user's question is outside Flox's scope, briefly note that and try to help anyway.
"""


def build_system_prompt(
    context: BuiltContext,
    skills: list[SkillPackage],
    intent: str,
) -> str:
    """Assemble the full system prompt from base + skills + RAG + user memory."""
    parts = [SYSTEM_PROMPT_BASE]

    # Inject skill knowledge
    for skill in skills:
        if skill.skill_md:
            role_label = "Primary" if skill.role == "primary" else "Secondary"
            parts.append(
                f"\n--- {role_label} Skill: {skill.name} ---\n{skill.skill_md}\n"
            )

    # Inject RAG results
    if context.rag_results:
        rag_text = "\n--- Relevant Knowledge ---\n"
        for i, result in enumerate(context.rag_results, 1):
            content = result.get("content", "")
            source = result.get("source_file", "unknown")
            rag_text += f"\n[{i}] (from {source}):\n{content}\n"
        parts.append(rag_text)

    # Inject user memory context
    if context.user_memory:
        mem = context.user_memory
        mem_text = "\n--- User Context ---\n"
        if skill_level := mem.get("skill_level"):
            mem_text += f"User skill level: {skill_level}\n"
        if projects := mem.get("projects"):
            mem_text += f"Known projects: {projects}\n"
        parts.append(mem_text)

    # Intent-specific guidance
    if intent == "teaching":
        parts.append(
            "\nThe user is looking to learn. Explain concepts step-by-step, "
            "use examples, and check understanding.\n"
        )
    elif intent == "diagnostic":
        parts.append(
            "\nThe user has a problem to debug. Ask clarifying questions if needed, "
            "suggest diagnostic steps, and provide fixes.\n"
        )

    return "\n".join(parts)


def build_messages(
    text: str,
    code_blocks: list[str] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Format messages for the Anthropic API.

    Returns a list of {"role": "user"|"assistant", "content": "..."} dicts.
    """
    messages: list[dict[str, str]] = []

    # Add conversation history
    if history:
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", msg.get("text", ""))
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    # Build current user message
    user_content = text
    if code_blocks:
        for block in code_blocks:
            user_content += f"\n\n```\n{block}\n```"

    messages.append({"role": "user", "content": user_content})

    return messages
