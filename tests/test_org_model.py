"""Tests for Organization/OrgMember models and Vote.org_id."""

from __future__ import annotations

import uuid

import pytest

from tests.factories import make_org, make_org_member, make_vote


class TestOrganizationModel:
    """Organization and OrgMember CRUD via SQLAlchemy."""

    @pytest.mark.asyncio
    async def test_create_organization(self, db_session):
        from src.db.models import Organization

        org = Organization(name="Acme Corp", slug="acme")
        db_session.add(org)
        await db_session.flush()

        assert org.id is not None
        assert org.name == "Acme Corp"
        assert org.slug == "acme"
        assert org.created_at is not None

    @pytest.mark.asyncio
    async def test_org_slug_unique(self, db_session):
        from sqlalchemy.exc import IntegrityError
        from src.db.models import Organization

        org1 = Organization(name="Acme 1", slug="acme")
        org2 = Organization(name="Acme 2", slug="acme")
        db_session.add(org1)
        await db_session.flush()

        db_session.add(org2)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_create_org_member(self, db_session):
        from src.db.models import Organization, OrgMember

        org = Organization(name="Acme", slug="acme-member-test")
        db_session.add(org)
        await db_session.flush()

        member = OrgMember(
            org_id=str(org.id),
            canonical_user_id="usr_alice",
            role="admin",
        )
        db_session.add(member)
        await db_session.flush()

        assert member.id is not None
        assert member.role == "admin"
        assert member.joined_at is not None

    @pytest.mark.asyncio
    async def test_vote_accepts_null_org_id(self, db_session):
        from src.db.models import Vote

        vote = Vote(
            message_id=uuid.uuid4(),
            conversation_id="conv_1",
            user_id="usr_1",
            vote="up",
            org_id=None,
        )
        db_session.add(vote)
        await db_session.flush()
        assert vote.org_id is None

    @pytest.mark.asyncio
    async def test_vote_accepts_org_id(self, db_session):
        from src.db.models import Vote

        vote = Vote(
            message_id=uuid.uuid4(),
            conversation_id="conv_2",
            user_id="usr_2",
            vote="up",
            org_id="org_acme",
        )
        db_session.add(vote)
        await db_session.flush()
        assert vote.org_id == "org_acme"


class TestEntitlementsOrgId:
    """Entitlements.org_id round-trips."""

    def test_org_id_default_none(self):
        from src.models.types import Entitlements
        e = Entitlements()
        assert e.org_id is None

    def test_org_id_set(self):
        from src.models.types import Entitlements
        e = Entitlements(org_id="org_acme")
        assert e.org_id == "org_acme"

    def test_org_id_roundtrip(self):
        from src.models.types import Entitlements
        e = Entitlements(org_id="org_123")
        dumped = e.model_dump()
        assert dumped["org_id"] == "org_123"
        e2 = Entitlements(**dumped)
        assert e2.org_id == "org_123"


class TestFactories:
    """Test factory helpers."""

    def test_make_org(self):
        org = make_org()
        assert org["name"] == "Acme Corp"
        assert "slug" in org

    def test_make_org_member(self):
        m = make_org_member(role="admin")
        assert m["role"] == "admin"
        assert "org_id" in m
