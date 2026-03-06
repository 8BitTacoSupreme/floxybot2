"""Tests for cross-channel identity model (T14)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from src.db.models import ChannelIdentity


class TestChannelIdentityModel:
    """Verify the ChannelIdentity ORM model."""

    @pytest.mark.asyncio
    async def test_create_identity(self, db_session):
        """Should create a channel identity record."""
        identity = ChannelIdentity(
            canonical_user_id="usr_alice",
            channel="slack",
            channel_user_id="U12345",
        )
        db_session.add(identity)
        await db_session.flush()

        result = await db_session.execute(
            select(ChannelIdentity).where(ChannelIdentity.canonical_user_id == "usr_alice")
        )
        row = result.scalar_one()
        assert row.channel == "slack"
        assert row.channel_user_id == "U12345"
        assert row.linked_at is not None

    @pytest.mark.asyncio
    async def test_same_user_multiple_channels(self, db_session):
        """Same canonical user can have identities on multiple channels."""
        db_session.add(ChannelIdentity(
            canonical_user_id="usr_bob", channel="slack", channel_user_id="U_SLACK"
        ))
        db_session.add(ChannelIdentity(
            canonical_user_id="usr_bob", channel="discord", channel_user_id="D_DISCORD"
        ))
        await db_session.flush()

        result = await db_session.execute(
            select(ChannelIdentity).where(ChannelIdentity.canonical_user_id == "usr_bob")
        )
        rows = result.scalars().all()
        assert len(rows) == 2
        channels = {r.channel for r in rows}
        assert channels == {"slack", "discord"}

    @pytest.mark.asyncio
    async def test_lookup_canonical_from_channel(self, db_session):
        """Should resolve canonical_user_id from channel + channel_user_id."""
        db_session.add(ChannelIdentity(
            canonical_user_id="usr_carol", channel="discord", channel_user_id="D_999"
        ))
        await db_session.flush()

        result = await db_session.execute(
            select(ChannelIdentity.canonical_user_id).where(
                ChannelIdentity.channel == "discord",
                ChannelIdentity.channel_user_id == "D_999",
            )
        )
        canonical = result.scalar_one()
        assert canonical == "usr_carol"
