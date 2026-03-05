"""Codex LLM backend — code generation, manifest editing, debugging.

Phase 1: Routes back to Claude with a note that Codex-specific features
are not yet available. Full Codex integration is Phase 4.
"""

from __future__ import annotations

import logging
from typing import Any

from ..models.types import BuiltContext, SkillPackage

logger = logging.getLogger(__name__)


async def call_codex(
    message: dict[str, Any],
    context: BuiltContext,
    skills: list[SkillPackage],
) -> dict[str, Any]:
    """Route code generation through Claude in Phase 1.

    Codex-specific system prompt and features are Phase 4.
    For now, we use Claude with a code-focused intent hint.
    """
    from .claude import call_claude

    logger.info("Codex not available in Phase 1, routing to Claude")
    return await call_claude(message, context, skills, intent="code_generation")
