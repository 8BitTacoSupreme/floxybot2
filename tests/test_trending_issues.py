"""Tests for trending issues detection consumer."""

from __future__ import annotations

import pytest

from jobs.trending_issues import TrendingIssuesConsumer


def _msg(text="how to install flox", timestamp=100.0):
    return {"content": {"text": text}, "timestamp": timestamp}


@pytest.mark.asyncio
async def test_spike_detected():
    """Spike in keyword frequency triggers trending alert."""
    consumer = TrendingIssuesConsumer()

    # First window: establish baseline with 1 message
    events = [_msg(text="install flox", timestamp=0)]
    # Process first to set baseline
    for ev in events:
        consumer.process_event(ev)

    # Manually set a low baseline for "install"
    consumer._baseline["install"] = 1

    # Now create a spike: 6 messages about "install" in next window
    spike_events = [
        _msg(text="install install install install install install", timestamp=14400 + i)
        for i in range(1)
    ]
    # Add to trigger window close
    spike_events.append(_msg(text="install " * 6, timestamp=14400 * 2 + 1))

    outputs = []
    for ev in spike_events:
        outputs.extend(consumer.process_event(ev))

    trending = [o for o in outputs if o["type"] == "trending_issues"]
    assert len(trending) >= 1
    kws = [t["keyword"] for t in trending[0]["trending"]]
    assert "install" in kws


@pytest.mark.asyncio
async def test_steady_state_not_flagged():
    """Steady keyword frequency doesn't trigger trending."""
    consumer = TrendingIssuesConsumer()

    # Set baseline
    consumer._baseline["install"] = 10

    # Same level of activity
    events = [_msg(text="install flox", timestamp=i * 100) for i in range(10)]
    outputs = await consumer.run_on_events(events)

    trending = [o for o in outputs if o["type"] == "trending_issues"]
    # Should not flag since count is not 5x baseline
    for t in trending:
        kws = [item["keyword"] for item in t["trending"]]
        assert "install" not in kws


@pytest.mark.asyncio
async def test_empty_safe():
    """Empty input doesn't crash."""
    consumer = TrendingIssuesConsumer()
    outputs = await consumer.run_on_events([])
    assert isinstance(outputs, list)
