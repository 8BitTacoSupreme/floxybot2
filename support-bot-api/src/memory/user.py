"""User memory — Tier 1 per-user real-time memory with PostgreSQL persistence."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import UserMemory

logger = logging.getLogger(__name__)


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

    await session.flush()
