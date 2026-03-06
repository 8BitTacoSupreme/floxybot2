"""System prompt assembly for Claude and Codex LLM calls."""

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

CODEX_SYSTEM_PROMPT = """You are FloxBot Codex, a code-generation backend for Flox — the universal package manager and environment management tool. You produce working, complete code output.

Your output style:
- Code-first. Minimal prose. Direct tone.
- Always output complete, working code blocks — never partial snippets or placeholders.
- When editing manifest.toml, show the complete relevant section, not diffs or fragments.
- Use Flox manifest.toml conventions throughout.

manifest.toml schema reference:
- [install.<pkg>] — package installation. Fields: pkg-path, version, priority.
  Example: [install.nodejs] / pkg-path = "nodejs_22"
- [hook] — lifecycle hooks. on-activate runs on every `flox activate`.
  Example: [hook] / on-activate = '''export PATH="$FLOX_ENV/bin:$PATH"'''
- [services.<name>] — long-running services managed by Flox.
  Fields: command, is-daemon, shutdown.
  Example: [services.api] / command = "uvicorn main:app --port 8000"
- [options] — environment-level settings.
  Fields: systems, allow-unfree, allow-broken, semver.allow-pre-release.

Rules:
- Never output incomplete code. If a section is too large, split into clearly labeled parts.
- Include shell commands in ```bash blocks and TOML in ```toml blocks.
- When generating manifest sections, always include the section header (e.g., [install], [hook]).
- Validate that generated manifests are syntactically correct TOML.
- If you need to show multiple files, label each clearly with its path.
"""

DIAGNOSTIC_PROMPT_SUFFIX = """
You are in diagnostic mode. Structure your response as:

1. **What I see** — Summarize the symptoms, error messages, and relevant context.
2. **What might be wrong** — List the most likely root causes, ranked by probability.
3. **Steps to fix** — Provide concrete, ordered steps to resolve the issue.

Suggest diagnostic commands the user can run to gather more information, using code blocks:
- `flox list` to check installed packages
- `flox activate -- <command>` to test in isolation
- `flox edit` to inspect the manifest
- Environment variable checks, log inspection, etc.

Be systematic. One hypothesis at a time. If you need more information to narrow down the cause, ask specific questions.
"""

TEACHING_PROMPT_SUFFIX = """
You are in teaching mode. Guide the user through learning step-by-step:

- Break complex topics into small, digestible steps.
- Use analogies and real-world comparisons to explain abstract concepts.
- Show working examples at each step — don't just describe, demonstrate.
- After explaining a concept, end with a "Try it yourself" prompt: suggest a small exercise or command the user can run to reinforce what they learned.
- Adjust depth and vocabulary based on the user's skill level:
  - Beginner: explain terminology, avoid jargon, use simple examples.
  - Intermediate: focus on patterns, best practices, and "why" not just "how".
  - Advanced: go deeper into internals, edge cases, and performance considerations.
- Encourage questions. Make it safe to not know things.
"""

CODE_GENERATION_PROMPT_SUFFIX = """
You are generating code. Follow these rules:

- Output complete, working code blocks — never partial snippets or pseudo-code.
- For manifest.toml changes, always show the full section (e.g., the entire [install] block, not just the new line).
- Validate that TOML output is syntactically correct.
- Include any necessary shell commands to apply the changes (e.g., `flox edit`, `flox install`).
- If the change spans multiple files, label each file clearly with its path.
- Prefer idiomatic Flox patterns: use `$FLOX_ENV`, `$FLOX_ENV_PROJECT`, `$FLOX_ENV_CACHE` over absolute paths.
- Test commands should be included when relevant (e.g., `flox activate -- python --version`).
"""

# Map intent strings to their prompt suffixes
_INTENT_SUFFIXES: dict[str, str] = {
    "diagnostic": DIAGNOSTIC_PROMPT_SUFFIX,
    "teaching": TEACHING_PROMPT_SUFFIX,
    "code_generation": CODE_GENERATION_PROMPT_SUFFIX,
    # "conversational" intentionally omitted — no suffix needed
}


def build_system_prompt(
    context: BuiltContext,
    skills: list[SkillPackage],
    intent: str,
    backend: str = "claude",
) -> str:
    """Assemble the full system prompt from base + skills + RAG + user memory.

    Args:
        context: Built context containing RAG results, user memory, project context.
        skills: Active skill packages for this turn (max 2).
        intent: Intent classification string — one of "conversational",
                "code_generation", "diagnostic", "teaching".
        backend: LLM backend — "claude" or "codex". Selects the base prompt.

    Returns:
        The assembled system prompt string.
    """
    # Select base prompt based on backend
    base = CODEX_SYSTEM_PROMPT if backend == "codex" else SYSTEM_PROMPT_BASE
    parts = [base]

    # Inject skill knowledge
    for skill in skills:
        if skill.skill_md:
            role_label = "Primary" if skill.role == "primary" else "Secondary"
            parts.append(
                f"\n--- {role_label} Skill: {skill.name} ---\n{skill.skill_md}\n"
            )

        # Inject skill diagnostic prompts when in diagnostic mode
        if intent == "diagnostic" and hasattr(skill, "prompts") and skill.prompts:
            diag_text = f"\n--- Diagnostic Prompts: {skill.name} ---\n"
            for prompt_fragment in skill.prompts:
                diag_text += f"{prompt_fragment}\n"
            parts.append(diag_text)

    # Inject RAG results with source labels and relevance scores
    if context.rag_results:
        rag_text = "\n--- Relevant Knowledge ---\n"
        for i, result in enumerate(context.rag_results, 1):
            content = result.get("content", "")
            source_label = result.get("source_label", result.get("source_file", "unknown"))
            similarity = result.get("similarity", 0.0)
            relevance_pct = int(similarity * 100)
            rag_text += f"\n[{i}] [{source_label}] (relevance: {relevance_pct}%):\n{content}\n"
        parts.append(rag_text)

    # Inject instance knowledge (Tier 2) if available
    if hasattr(context, "instance_knowledge") and context.instance_knowledge:
        inst = context.instance_knowledge
        inst_text = "\n--- Community-Validated Answers ---\n"
        for i, item in enumerate(inst, 1):
            question = item.get("query", item.get("question", ""))
            answer = item.get("response", item.get("answer", ""))
            similarity = item.get("similarity", 0)
            inst_text += f"\n[{i}] Q: {question}\n    A: {answer}\n    (Upvoted by community)\n"
        parts.append(inst_text)

    # Inject user memory context
    if context.user_memory:
        mem = context.user_memory
        mem_text = "\n--- User Context ---\n"
        if skill_level := mem.get("skill_level"):
            mem_text += f"User skill level: {skill_level}\n"
        if projects := mem.get("projects"):
            mem_text += f"Known projects: {projects}\n"
        parts.append(mem_text)

    # Inject project context (manifest, detected skills)
    if context.project_context:
        proj = context.project_context
        if proj.get("has_flox_env"):
            proj_text = "\n--- User's Project Context ---\n"
            proj_text += "The user is working in a directory with a Flox environment.\n"
            if manifest := proj.get("manifest"):
                proj_text += f"\nTheir manifest.toml:\n```toml\n{manifest}\n```\n"
            if detected := proj.get("detected_skills"):
                proj_text += f"Detected skills: {', '.join(detected)}\n"
            parts.append(proj_text)

    # Intent-specific guidance via suffix constants
    intent_lower = intent.lower() if intent else ""
    if intent_lower in _INTENT_SUFFIXES:
        parts.append(_INTENT_SUFFIXES[intent_lower])

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
