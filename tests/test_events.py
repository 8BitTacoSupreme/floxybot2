"""Tests for event publishing."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_inmemory_publisher_stores():
    """InMemoryPublisher stores events in memory."""
    from src.events.publisher import InMemoryPublisher

    pub = InMemoryPublisher()
    await pub.publish("test.topic", "key1", {"data": "hello"})
    await pub.publish("test.topic", "key2", {"data": "world"})
    await pub.publish("other.topic", "key3", {"data": "other"})

    assert len(pub.events) == 3
    assert len(pub.get_events("test.topic")) == 2
    assert len(pub.get_events("other.topic")) == 1


def test_kafka_publisher_init():
    """KafkaPublisher can be instantiated (doesn't connect until first publish)."""
    from src.events.publisher import KafkaPublisher

    pub = KafkaPublisher(bootstrap_servers="localhost:9092")
    assert pub._producer is None
    assert pub._bootstrap_servers == "localhost:9092"
