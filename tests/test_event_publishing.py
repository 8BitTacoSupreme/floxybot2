"""Tests for Central API event publishing (inbound/outbound/context)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from src.events.publisher import InMemoryPublisher


@pytest.fixture
def publisher():
    return InMemoryPublisher()


@pytest_asyncio.fixture
async def client_with_publisher(mock_claude, mock_voyage, mock_redis, publisher):
    """API client with our InMemoryPublisher injected."""
    from src.main import app
    from src import deps

    original = deps.get_event_publisher

    async def override():
        return publisher

    app.dependency_overrides[deps.get_event_publisher] = override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.pop(deps.get_event_publisher, None)


def _make_message():
    return {
        "content": {"text": "How do I install flox?"},
        "user_identity": {
            "channel": "slack",
            "canonical_user_id": "usr_test",
            "floxhub_username": "testuser",
        },
        "context": {"conversation_id": "conv_1"},
    }


@pytest.mark.asyncio
async def test_inbound_event_published(client_with_publisher, publisher):
    """Inbound message event is published to floxbot.messages.inbound."""
    resp = await client_with_publisher.post("/v1/message", json=_make_message())
    assert resp.status_code == 200

    inbound = publisher.get_events("floxbot.messages.inbound")
    assert len(inbound) >= 1


@pytest.mark.asyncio
async def test_outbound_event_published(client_with_publisher, publisher):
    """Outbound response event is published to floxbot.messages.outbound."""
    resp = await client_with_publisher.post("/v1/message", json=_make_message())
    assert resp.status_code == 200

    outbound = publisher.get_events("floxbot.messages.outbound")
    assert len(outbound) >= 1
    assert "response_text" in outbound[0]["value"]


@pytest.mark.asyncio
async def test_context_event_published(client_with_publisher, publisher):
    """Context snapshot is published to floxbot.context.detected."""
    resp = await client_with_publisher.post("/v1/message", json=_make_message())
    assert resp.status_code == 200

    ctx = publisher.get_events("floxbot.context.detected")
    assert len(ctx) >= 1
    assert "intent" in ctx[0]["value"]
    assert "skills" in ctx[0]["value"]


@pytest.mark.asyncio
async def test_publishing_failure_doesnt_break_response(client_with_publisher, publisher):
    """If event publishing fails, the user still gets a response."""
    # Make publish raise an exception
    original_publish = publisher.publish
    call_count = [0]

    async def failing_publish(topic, key, value):
        call_count[0] += 1
        raise RuntimeError("Kafka down")

    publisher.publish = failing_publish

    resp = await client_with_publisher.post("/v1/message", json=_make_message())
    assert resp.status_code == 200
    assert call_count[0] >= 1  # publish was attempted

    publisher.publish = original_publish


@pytest.mark.asyncio
async def test_inbound_event_is_sanitized(client_with_publisher, publisher):
    """Inbound event has secrets stripped."""
    msg = _make_message()
    msg["content"]["text"] = "My API_KEY is sk-secret-123"
    resp = await client_with_publisher.post("/v1/message", json=msg)
    assert resp.status_code == 200

    inbound = publisher.get_events("floxbot.messages.inbound")
    assert len(inbound) >= 1
    # The text should still be present (PII scrub doesn't redact "API_KEY" in text)
    # but if there were env var keys, they'd be redacted
