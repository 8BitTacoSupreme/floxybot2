"""Phase 5 integration tests — end-to-end event pipeline."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from config.topics import ALL_TOPIC_NAMES, TOPIC_CONFIGS
from src.events.publisher import InMemoryPublisher
from src.events.sanitizer import sanitize_message_for_event


@pytest.fixture
def publisher():
    return InMemoryPublisher()


@pytest_asyncio.fixture
async def client_with_publisher(mock_claude, mock_voyage, mock_redis, publisher):
    from src.main import app
    from src import deps

    async def override():
        return publisher

    app.dependency_overrides[deps.get_event_publisher] = override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.pop(deps.get_event_publisher, None)


def test_all_nine_topics_defined():
    """Architecture specifies 9 topics — all are defined."""
    assert len(ALL_TOPIC_NAMES) == 9
    assert len(TOPIC_CONFIGS) == 9


def test_sanitizer_applied_to_message():
    """sanitize_message_for_event strips secrets and truncates."""
    msg = {
        "content": {"text": "x" * 3000},
        "env": {"API_KEY": "secret"},
    }
    result = sanitize_message_for_event(msg)
    assert result["env"]["API_KEY"] == "[REDACTED]"
    assert len(result["content"]["text"]) < 3000


@pytest.mark.asyncio
async def test_end_to_end_message_publishes_events(client_with_publisher, publisher):
    """Full message → inbound + context + outbound events published."""
    msg = {
        "content": {"text": "How do I install flox?"},
        "user_identity": {
            "channel": "cli",
            "canonical_user_id": "usr_e2e",
            "floxhub_username": "e2euser",
        },
    }
    resp = await client_with_publisher.post("/v1/message", json=msg)
    assert resp.status_code == 200

    # All 3 event types should be published
    inbound = publisher.get_events("floxbot.messages.inbound")
    outbound = publisher.get_events("floxbot.messages.outbound")
    context = publisher.get_events("floxbot.context.detected")

    assert len(inbound) >= 1
    assert len(outbound) >= 1
    assert len(context) >= 1


@pytest.mark.asyncio
async def test_consumer_processes_published_events(client_with_publisher, publisher):
    """Published inbound events can be consumed by cross-channel consumer."""
    from jobs.cross_channel_correlation import CrossChannelConsumer

    # Send a message to generate an inbound event
    msg = {
        "content": {"text": "Help with k8s"},
        "user_identity": {
            "channel": "slack",
            "canonical_user_id": "usr_pipe",
            "floxhub_username": "pipeuser",
        },
    }
    resp = await client_with_publisher.post("/v1/message", json=msg)
    assert resp.status_code == 200

    # Feed published events to the consumer
    inbound = publisher.get_events("floxbot.messages.inbound")
    assert len(inbound) >= 1

    consumer = CrossChannelConsumer()
    # Enrich with timestamp for windowing
    events = [{**e["value"], "timestamp": i * 100} for i, e in enumerate(inbound)]
    outputs = await consumer.run_on_events(events)
    # Consumer should process without error (no XC since single channel)
    assert isinstance(outputs, list)
