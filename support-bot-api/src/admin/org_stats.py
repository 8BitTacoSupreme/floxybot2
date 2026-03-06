"""Org stats and member queries for the admin dashboard API."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import OrgMember, Vote


async def get_org_stats(org_id: str, session: AsyncSession) -> dict[str, Any]:
    """Get org-scoped usage statistics.

    Returns vote count, skill breakdown, and member count.
    """
    # Vote count
    vote_count_result = await session.execute(
        select(func.count(Vote.id)).where(Vote.org_id == org_id)
    )
    vote_count = vote_count_result.scalar() or 0

    # Skill breakdown from votes
    votes_result = await session.execute(
        select(Vote.skills_used).where(Vote.org_id == org_id)
    )
    skill_counter: Counter = Counter()
    for (skills_used,) in votes_result.all():
        if isinstance(skills_used, list):
            for skill in skills_used:
                skill_counter[skill] += 1
        elif isinstance(skills_used, dict):
            for skill in skills_used:
                skill_counter[skill] += 1

    # Member count
    member_count_result = await session.execute(
        select(func.count(OrgMember.id)).where(OrgMember.org_id == org_id)
    )
    member_count = member_count_result.scalar() or 0

    return {
        "org_id": org_id,
        "vote_count": vote_count,
        "skill_breakdown": dict(skill_counter),
        "member_count": member_count,
    }


async def get_org_members(org_id: str, session: AsyncSession) -> list[dict[str, Any]]:
    """Get members of an organization."""
    result = await session.execute(
        select(OrgMember).where(OrgMember.org_id == org_id)
    )
    members = result.scalars().all()

    return [
        {
            "id": str(m.id),
            "canonical_user_id": m.canonical_user_id,
            "role": m.role,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
        }
        for m in members
    ]
