"""Tests for vote and feedback recording."""

from __future__ import annotations

import uuid

import pytest

from tests.factories import make_feedback, make_vote


@pytest.mark.asyncio
async def test_record_vote_valid():
    """Valid vote data → ok status."""
    from src.memory.votes import record_vote

    vote = make_vote()
    result = await record_vote(vote)
    assert result["status"] == "ok"
    assert "vote_id" in result


@pytest.mark.asyncio
async def test_record_vote_invalid():
    """Invalid vote data → error."""
    from src.memory.votes import record_vote

    result = await record_vote({"bad": "data"})
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_record_feedback_valid():
    """Valid feedback data → ok status."""
    from src.memory.votes import record_feedback

    fb = make_feedback()
    result = await record_feedback(fb)
    assert result["status"] == "ok"
    assert "feedback_id" in result


@pytest.mark.asyncio
async def test_record_feedback_invalid():
    """Invalid feedback → error."""
    from src.memory.votes import record_feedback

    result = await record_feedback({"missing": "fields"})
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_vote_publishes_kafka_event(in_memory_publisher):
    """Vote publishes to Kafka topic via InMemoryPublisher."""
    from src.memory.votes import record_vote

    vote = make_vote()
    result = await record_vote(vote, publisher=in_memory_publisher)
    assert result["status"] == "ok"

    events = in_memory_publisher.get_events("floxbot.votes")
    assert len(events) == 1
    assert events[0]["value"]["vote"] == "up"


@pytest.mark.asyncio
async def test_feedback_publishes_kafka_event(in_memory_publisher):
    """Feedback publishes to Kafka topic."""
    from src.memory.votes import record_feedback

    fb = make_feedback()
    result = await record_feedback(fb, publisher=in_memory_publisher)
    assert result["status"] == "ok"

    events = in_memory_publisher.get_events("floxbot.feedback")
    assert len(events) == 1
    assert events[0]["value"]["category"] == "helpful"
