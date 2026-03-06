"""Phase 6 integration tests."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from src.db.models import Organization, OrgMember, Vote
from src.models.types import Entitlements


class TestOrgWorkflow:
    """Org created → member added → vote with org_id → admin stats reflect it."""

    @pytest.mark.asyncio
    async def test_full_org_workflow(self, db_session):
        # Create org
        org = Organization(name="Integration Corp", slug=f"integ-{uuid.uuid4().hex[:8]}")
        db_session.add(org)
        await db_session.flush()

        # Add member
        member = OrgMember(
            org_id=str(org.id),
            canonical_user_id="usr_integ",
            role="admin",
        )
        db_session.add(member)
        await db_session.flush()

        # Create vote with org_id
        vote = Vote(
            message_id=uuid.uuid4(),
            conversation_id="conv_integ",
            user_id="usr_integ",
            vote="up",
            query_text="integration test",
            response_text="it works",
            org_id=str(org.id),
            skills_used=["k8s"],
        )
        db_session.add(vote)
        await db_session.flush()

        # Check admin stats
        from src.admin.org_stats import get_org_stats, get_org_members

        stats = await get_org_stats(str(org.id), db_session)
        assert stats["vote_count"] == 1
        assert stats["member_count"] == 1
        assert "k8s" in stats["skill_breakdown"]

        members = await get_org_members(str(org.id), db_session)
        assert len(members) == 1
        assert members[0]["canonical_user_id"] == "usr_integ"


class TestCustomSkillIntegration:
    """Custom skill path searched for enterprise entitlement."""

    @pytest.mark.asyncio
    async def test_enterprise_searches_custom_path(self):
        from src.skills.loader import detect_and_load_skills
        from src.models.types import BuiltContext

        with tempfile.TemporaryDirectory() as custom_dir:
            skill_dir = Path(custom_dir) / "enterprise-tool"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Enterprise Tool\nSpecial content.")

            ent = Entitlements(skill_access="custom")

            with patch("src.config.settings.SKILLS_PATH", "/nonexistent"), \
                 patch("src.config.settings.CUSTOM_SKILLS_PATH", custom_dir):
                context = BuiltContext(
                    project_context={"detected_skills": ["enterprise-tool"]}
                )
                skills = await detect_and_load_skills(context, entitlements=ent)

            assert any(s.name == "enterprise-tool" for s in skills)


class TestTelemetryIntegration:
    """Telemetry consumer processes events."""

    @pytest.mark.asyncio
    async def test_telemetry_consumer_processes(self):
        from jobs.telemetry_consumer import TelemetryConsumer

        consumer = TelemetryConsumer()
        events = [
            {"timestamp": 1000000.0, "mode": "ask", "skills": ["core-canon"], "duration_seconds": 3.0},
            {"timestamp": 1000010.0, "mode": "chat", "skills": ["k8s"], "duration_seconds": 7.0},
        ]
        results = await consumer.run_on_events(events)
        assert len(results) >= 1
        assert results[0]["total_events"] == 2


class TestEntitlementsOrgIdIntegration:
    """Entitlements.org_id flows through the system."""

    def test_enterprise_tier_has_org_id_field(self):
        from src.auth.entitlements import TIER_CONFIGS
        ent = TIER_CONFIGS["enterprise"]
        # org_id defaults to None on the tier config (set per-user at runtime)
        assert hasattr(ent, "org_id")
