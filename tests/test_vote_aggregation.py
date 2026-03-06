"""Tests for vote aggregation consumer."""

from __future__ import annotations

import pytest

from jobs.vote_aggregation import VoteAggregationConsumer


def _vote(skill="k8s", topic="install", vote="up", user="u1", timestamp=100.0):
    return {
        "skill": skill,
        "topic": topic,
        "vote": vote,
        "user_id": user,
        "timestamp": timestamp,
    }


@pytest.mark.asyncio
async def test_correct_vote_counts():
    """Hourly aggregate has correct per-skill vote counts."""
    consumer = VoteAggregationConsumer()
    events = [
        _vote(skill="k8s", vote="up", timestamp=100),
        _vote(skill="k8s", vote="up", timestamp=200),
        _vote(skill="terraform", vote="down", timestamp=300),
        # Next hour — triggers window close
        _vote(skill="k8s", vote="up", timestamp=3700),
    ]
    outputs = await consumer.run_on_events(events)

    hourly = [o for o in outputs if o["type"] == "hourly_vote_aggregate"]
    assert len(hourly) >= 1
    first = hourly[0]
    assert first["skill_votes"]["k8s"] == 2
    assert first["skill_votes"]["terraform"] == 1
    assert first["upvotes"] == 2
    assert first["downvotes"] == 1


@pytest.mark.asyncio
async def test_anomaly_detected_on_spike():
    """Anomaly flagged when downvote rate exceeds 2x baseline (30%)."""
    consumer = VoteAggregationConsumer()
    # All downvotes = 100% downvote rate > 30% threshold
    events = [
        _vote(vote="down", user="u1", timestamp=100),
        _vote(vote="down", user="u2", timestamp=200),
        _vote(vote="down", user="u3", timestamp=300),
        # Trigger window close
        _vote(vote="up", timestamp=3700),
    ]
    outputs = await consumer.run_on_events(events)

    # Check the daily trend (from flush)
    trends = [o for o in outputs if o["type"] == "daily_vote_trend"]
    assert len(trends) >= 1
    # At least one should detect anomaly
    assert any(t["anomaly_detected"] for t in trends)


@pytest.mark.asyncio
async def test_no_anomaly_normal_votes():
    """Normal vote patterns don't trigger anomaly."""
    consumer = VoteAggregationConsumer()
    # Mostly upvotes
    events = [
        _vote(vote="up", timestamp=100),
        _vote(vote="up", timestamp=200),
        _vote(vote="up", timestamp=300),
        _vote(vote="up", timestamp=400),
        _vote(vote="down", timestamp=500),  # 20% downvote rate
    ]
    outputs = await consumer.run_on_events(events)

    trends = [o for o in outputs if o["type"] == "daily_vote_trend"]
    for t in trends:
        assert not t["anomaly_detected"]


@pytest.mark.asyncio
async def test_empty_window_safe():
    """Consumer handles empty event list gracefully."""
    consumer = VoteAggregationConsumer()
    outputs = await consumer.run_on_events([])
    # flush on empty should not crash
    assert isinstance(outputs, list)


@pytest.mark.asyncio
async def test_flush_returns_remaining():
    """Flush returns aggregates for unclosed windows."""
    consumer = VoteAggregationConsumer()
    # All in same window — no auto-close
    events = [_vote(timestamp=100), _vote(timestamp=200)]
    outputs = await consumer.run_on_events(events)
    # Should have flush outputs
    assert len(outputs) >= 1
