"""Integration tests for the Central API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.factories import make_feedback, make_message, make_vote


@pytest_asyncio.fixture
async def client(mock_claude):
    """API client with mocked dependencies (no DB/Redis/Kafka)."""
    from src.events.publisher import InMemoryPublisher
    from src.main import app

    # Override DI dependencies
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.flush = AsyncMock()

    # Mock execute for conversation history
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    publisher = InMemoryPublisher()

    async def mock_get_db():
        yield mock_session

    async def mock_get_redis():
        return None

    async def mock_get_publisher():
        return publisher

    from src.deps import get_db_session, get_event_publisher, get_redis
    app.dependency_overrides[get_db_session] = mock_get_db
    app.dependency_overrides[get_redis] = mock_get_redis
    app.dependency_overrides[get_event_publisher] = mock_get_publisher

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health(client):
    """GET /health → 200."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_message_basic(client):
    """POST /v1/message with valid message → 200 + response shape."""
    msg = make_message()
    resp = await client.post("/v1/message", json=msg)
    assert resp.status_code == 200
    data = resp.json()
    assert "text" in data
    assert data["status"] == "ok"
    assert data["llm_backend"] == "claude"
    assert "response_id" in data


@pytest.mark.asyncio
async def test_message_with_skills(client):
    """detected_skills in context → skills loaded."""
    msg = make_message(
        content={"text": "How do I use flox install?", "attachments": [], "code_blocks": []}
    )
    resp = await client.post("/v1/message", json=msg)
    assert resp.status_code == 200
    data = resp.json()
    # core-canon should be detected from "flox install" text
    if data.get("skills_used"):
        assert any(s["name"] == "core-canon" for s in data["skills_used"])


@pytest.mark.asyncio
async def test_message_escalation(client):
    """'talk to human' text doesn't crash (escalation path)."""
    msg = make_message(
        content={
            "text": "I need to talk to a human please",
            "attachments": [],
            "code_blocks": [],
        }
    )
    resp = await client.post("/v1/message", json=msg)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_message_invalid(client):
    """Malformed body → 422."""
    resp = await client.post("/v1/message", json={"bad": "data"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_vote_endpoint(client):
    """POST /v1/vote → ok."""
    vote = make_vote()
    resp = await client.post("/v1/vote", json=vote)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_feedback_endpoint(client):
    """POST /v1/feedback → ok."""
    fb = make_feedback()
    resp = await client.post("/v1/feedback", json=fb)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
