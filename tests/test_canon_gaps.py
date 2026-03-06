"""Tests for canon gap detection consumer."""

from __future__ import annotations

import pytest

from jobs.canon_gap_detection import CanonGapConsumer


def _vote(skill="k8s", vote="up", timestamp=100.0):
    return {"skill": skill, "vote": vote, "timestamp": timestamp}


@pytest.mark.asyncio
async def test_high_downvote_skill_flagged():
    """Skill with >30% downvote rate is flagged."""
    consumer = CanonGapConsumer()
    events = [
        _vote(skill="terraform", vote="down", timestamp=100),
        _vote(skill="terraform", vote="down", timestamp=200),
        _vote(skill="terraform", vote="up", timestamp=300),
        # Next day — triggers window close
        _vote(skill="k8s", vote="up", timestamp=86500),
    ]
    outputs = await consumer.run_on_events(events)

    gaps = [o for o in outputs if o["type"] == "canon_gap_detected"]
    assert len(gaps) >= 1
    flagged_names = [s["skill"] for s in gaps[0]["flagged_skills"]]
    assert "terraform" in flagged_names
    tf = [s for s in gaps[0]["flagged_skills"] if s["skill"] == "terraform"][0]
    assert tf["downvote_rate"] > 0.3


@pytest.mark.asyncio
async def test_low_downvote_not_flagged():
    """Skill with low downvote rate is not flagged."""
    consumer = CanonGapConsumer()
    events = [
        _vote(skill="k8s", vote="up", timestamp=100),
        _vote(skill="k8s", vote="up", timestamp=200),
        _vote(skill="k8s", vote="up", timestamp=300),
        _vote(skill="k8s", vote="down", timestamp=400),  # 25%
    ]
    outputs = await consumer.run_on_events(events)

    gaps = [o for o in outputs if o["type"] == "canon_gap_detected"]
    # Either no gaps or k8s should not be in flagged
    for g in gaps:
        flagged_names = [s["skill"] for s in g["flagged_skills"]]
        assert "k8s" not in flagged_names


@pytest.mark.asyncio
async def test_empty_window_safe():
    """Empty input doesn't crash."""
    consumer = CanonGapConsumer()
    outputs = await consumer.run_on_events([])
    assert isinstance(outputs, list)
