"""Tests for admin dashboard API endpoints."""

from __future__ import annotations

import uuid

import pytest

from src.admin.org_stats import get_org_members, get_org_stats
from src.db.models import OrgMember, Vote
from src.models.types import Entitlements


class TestAdminAuthGate:
    """Auth gate checks for admin_dashboard feature."""

    def test_enterprise_has_admin_dashboard(self):
        from src.auth.entitlements import TIER_CONFIGS
        ent = TIER_CONFIGS["enterprise"]
        assert "admin_dashboard" in ent.features

    def test_pro_lacks_admin_dashboard(self):
        from src.auth.entitlements import TIER_CONFIGS
        ent = TIER_CONFIGS["pro"]
        assert "admin_dashboard" not in ent.features

    def test_community_lacks_admin_dashboard(self):
        from src.auth.entitlements import TIER_CONFIGS
        ent = TIER_CONFIGS["community"]
        assert "admin_dashboard" not in ent.features


class TestOrgStats:
    @pytest.mark.asyncio
    async def test_stats_returns_expected_shape(self, db_session):
        stats = await get_org_stats("org_test", db_session)
        assert "org_id" in stats
        assert "vote_count" in stats
        assert "skill_breakdown" in stats
        assert "member_count" in stats

    @pytest.mark.asyncio
    async def test_empty_org_returns_zeros(self, db_session):
        stats = await get_org_stats("org_nonexistent", db_session)
        assert stats["vote_count"] == 0
        assert stats["member_count"] == 0
        assert stats["skill_breakdown"] == {}

    @pytest.mark.asyncio
    async def test_stats_with_data(self, db_session):
        # Add a member
        member = OrgMember(org_id="org_stats", canonical_user_id="usr_a", role="member")
        db_session.add(member)

        # Add a vote
        vote = Vote(
            message_id=uuid.uuid4(),
            conversation_id="conv_stats",
            user_id="usr_a",
            vote="up",
            org_id="org_stats",
            skills_used=["k8s", "terraform"],
        )
        db_session.add(vote)
        await db_session.flush()

        stats = await get_org_stats("org_stats", db_session)
        assert stats["vote_count"] == 1
        assert stats["member_count"] == 1
        assert "k8s" in stats["skill_breakdown"]


class TestOrgMembers:
    @pytest.mark.asyncio
    async def test_members_scoped_by_org(self, db_session):
        m1 = OrgMember(org_id="org_a", canonical_user_id="usr_1", role="admin")
        m2 = OrgMember(org_id="org_b", canonical_user_id="usr_2", role="member")
        db_session.add_all([m1, m2])
        await db_session.flush()

        members_a = await get_org_members("org_a", db_session)
        assert len(members_a) == 1
        assert members_a[0]["canonical_user_id"] == "usr_1"

        members_b = await get_org_members("org_b", db_session)
        assert len(members_b) == 1

    @pytest.mark.asyncio
    async def test_empty_org_returns_empty(self, db_session):
        members = await get_org_members("org_empty", db_session)
        assert members == []
