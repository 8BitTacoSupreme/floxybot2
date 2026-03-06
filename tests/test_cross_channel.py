"""Tests for cross-channel correlation consumer."""

from __future__ import annotations

import pytest

from jobs.cross_channel_correlation import CrossChannelConsumer


def _msg(channel="slack", user_id="usr_1", text="how to install flox", timestamp=100.0):
    return {
        "user_identity": {"canonical_user_id": user_id, "channel": channel},
        "content": {"text": text},
        "timestamp": timestamp,
    }


@pytest.mark.asyncio
async def test_two_channels_within_30min():
    """2 distinct channels within 30min = cross-channel event."""
    consumer = CrossChannelConsumer()
    events = [
        _msg(channel="slack", user_id="u1", timestamp=100),
        _msg(channel="discord", user_id="u1", timestamp=600),
        # 31 min gap to close the session
        _msg(channel="slack", user_id="u1", timestamp=2500),
    ]
    outputs = await consumer.run_on_events(events)

    xc = [o for o in outputs if o["type"] == "cross_channel_session"]
    assert len(xc) >= 1
    assert set(xc[0]["channels"]) == {"slack", "discord"}
    assert xc[0]["user_id"] == "u1"


@pytest.mark.asyncio
async def test_single_channel_no_event():
    """1 channel only = no cross-channel event."""
    consumer = CrossChannelConsumer()
    events = [
        _msg(channel="slack", user_id="u1", timestamp=100),
        _msg(channel="slack", user_id="u1", timestamp=600),
    ]
    outputs = await consumer.run_on_events(events)

    xc = [o for o in outputs if o["type"] == "cross_channel_session"]
    assert len(xc) == 0


@pytest.mark.asyncio
async def test_31min_gap_closes_session():
    """31 min gap closes a session, next message starts new session."""
    consumer = CrossChannelConsumer()
    events = [
        _msg(channel="slack", user_id="u1", timestamp=0),
        # 31 min gap (1860 seconds)
        _msg(channel="slack", user_id="u1", timestamp=1860),
    ]
    outputs = await consumer.run_on_events(events)

    # The first session (single event) should be closed
    # Neither session has 2+ channels, so no XC events
    xc = [o for o in outputs if o["type"] == "cross_channel_session"]
    assert len(xc) == 0


@pytest.mark.asyncio
async def test_includes_topic_overlap():
    """Cross-channel event includes keyword overlap."""
    consumer = CrossChannelConsumer()
    events = [
        _msg(channel="slack", user_id="u1", text="how to install flox", timestamp=100),
        _msg(channel="discord", user_id="u1", text="install flox on mac", timestamp=600),
        _msg(channel="slack", user_id="u1", timestamp=2500),  # close session
    ]
    outputs = await consumer.run_on_events(events)

    xc = [o for o in outputs if o["type"] == "cross_channel_session"]
    assert len(xc) >= 1
    # "install" and "flox" should appear in overlap
    assert any(kw in xc[0]["topic_overlap"] for kw in ["install", "flox"])
