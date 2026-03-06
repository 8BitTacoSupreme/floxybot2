"""User memory — Tier 1 per-user real-time memory with PostgreSQL persistence."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import UserMemory

logger = logging.getLogger(__name__)

MAX_RECENT_SKILLS = 10


async def get_user_memory(
    canonical_user_id: str,
    session: AsyncSession | None = None,
) -> dict[str, Any]:
    """Retrieve user memory: projects, skill level, past issues, preferences."""
    if session is None:
        return {}

    stmt = select(UserMemory).where(UserMemory.canonical_user_id == canonical_user_id)
    result = await session.execute(stmt)
    memory = result.scalar_one_or_none()

    if memory is None:
        return {}

    return {
        "canonical_user_id": memory.canonical_user_id,
        "skill_level": memory.skill_level,
        "projects": memory.projects or {},
        "past_issues": memory.past_issues or {},
        "preferences": memory.preferences or {},
        "recent_skills": memory.recent_skills or [],
        "interaction_count": memory.interaction_count or 0,
    }


async def update_user_memory(
    canonical_user_id: str,
    updates: dict[str, Any],
    session: AsyncSession | None = None,
) -> None:
    """Update user memory after an interaction.

    Creates the record if it doesn't exist, merges JSONB fields if it does.
    """
    if session is None:
        return

    stmt = select(UserMemory).where(UserMemory.canonical_user_id == canonical_user_id)
    result = await session.execute(stmt)
    memory = result.scalar_one_or_none()

    if memory is None:
        # Create new memory record
        memory = UserMemory(
            canonical_user_id=canonical_user_id,
            skill_level=updates.get("skill_level", "beginner"),
            projects=updates.get("projects", {}),
            past_issues=updates.get("past_issues", {}),
            preferences=updates.get("preferences", {}),
            recent_skills=updates.get("recent_skills", []),
            interaction_count=updates.get("interaction_count", 1),
        )
        session.add(memory)
    else:
        # Merge updates into existing record
        if "skill_level" in updates:
            memory.skill_level = updates["skill_level"]
        if "projects" in updates:
            merged = dict(memory.projects or {})
            merged.update(updates["projects"])
            memory.projects = merged
        if "past_issues" in updates:
            merged = dict(memory.past_issues or {})
            merged.update(updates["past_issues"])
            memory.past_issues = merged
        if "preferences" in updates:
            merged = dict(memory.preferences or {})
            merged.update(updates["preferences"])
            memory.preferences = merged
        if "recent_skills" in updates:
            # Prepend new skills, dedup, keep last MAX_RECENT_SKILLS
            existing = list(memory.recent_skills or [])
            new_skills = updates["recent_skills"]
            merged = []
            seen = set()
            for s in new_skills + existing:
                if s not in seen:
                    merged.append(s)
                    seen.add(s)
            memory.recent_skills = merged[:MAX_RECENT_SKILLS]
        if "interaction_count" in updates:
            memory.interaction_count = (memory.interaction_count or 0) + 1

    await session.flush()


def build_memory_update(
    response: dict[str, Any],
    message: dict[str, Any],
    intent: str,
) -> dict[str, Any]:
    """Build a memory update dict from an interaction.

    Called after every successful LLM response. Extracts skills used,
    project context, and infers skill level from interaction count.
    """
    updates: dict[str, Any] = {}

    # Track skills used
    skills_used = response.get("skills_used", [])
    if skills_used:
        updates["recent_skills"] = [
            s["name"] if isinstance(s, dict) else s for s in skills_used
        ]

    # Track interaction count (triggers +1 in update_user_memory)
    updates["interaction_count"] = 1

    # Extract project context
    project = message.get("context", {}).get("project", {})
    if project.get("detected_skills"):
        projects = {}
        for skill in project["detected_skills"]:
            projects[skill] = {"last_seen": "recent"}
        updates["projects"] = projects

    # Infer skill level from interaction patterns
    code_blocks = message.get("content", {}).get("code_blocks", [])
    has_manifest = bool(project.get("manifest"))

    if code_blocks or has_manifest:
        # Users who send code/manifests are at least intermediate
        updates["skill_level"] = "intermediate"

    return updates


def infer_skill_level(interaction_count: int, has_code: bool = False) -> str:
    """Infer skill level from interaction count and signals."""
    if has_code and interaction_count >= 10:
        return "advanced"
    if has_code or interaction_count >= 10:
        return "intermediate"
    return "beginner"
