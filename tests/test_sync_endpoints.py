"""Tests for Phase 2 sync API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.factories import make_vote


@pytest_asyncio.fixture
async def client(mock_claude):
    """API client with mocked dependencies (no real DB/Redis/Kafka)."""
    from src.events.publisher import InMemoryPublisher
    from src.main import app

    from unittest.mock import MagicMock

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()  # sync method

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value = mock_scalars
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


class TestCanonSync:
    @pytest.mark.asyncio
    async def test_canon_sync_empty(self, client):
        resp = await client.get("/v1/canon/sync?since=2000-01-01T00:00:00Z")
        assert resp.status_code == 200
        data = resp.json()
        assert "chunks" in data
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_canon_sync_with_skills_filter(self, client):
        resp = await client.get("/v1/canon/sync?since=2000-01-01T00:00:00Z&skills=core-canon,skill-k8s")
        assert resp.status_code == 200
        data = resp.json()
        assert "chunks" in data

    @pytest.mark.asyncio
    async def test_canon_sync_pagination(self, client):
        resp = await client.get("/v1/canon/sync?since=2000-01-01T00:00:00Z&limit=10&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 0


class TestMemoryEndpoints:
    @pytest.mark.asyncio
    async def test_get_memory_empty(self, client):
        resp = await client.get("/v1/memory/usr_test1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "usr_test1"

    @pytest.mark.asyncio
    async def test_put_memory(self, client):
        resp = await client.put(
            "/v1/memory/usr_test1",
            json={"skill_level": "intermediate"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestBatchVotes:
    @pytest.mark.asyncio
    async def test_batch_votes_empty(self, client):
        resp = await client.post("/v1/votes/batch", json=[])
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_batch_votes_array(self, client):
        votes = [make_vote(), make_vote()]
        resp = await client.post("/v1/votes/batch", json=votes)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2


class TestTickets:
    @pytest.mark.asyncio
    async def test_create_ticket(self, client):
        resp = await client.post("/v1/tickets", json={
            "user_id": "usr_test1",
            "title": "Test ticket",
            "context_bundle": {"env": "test"},
            "priority": "high",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "ticket_id" in data
        assert data["priority"] == "high"

    @pytest.mark.asyncio
    async def test_create_ticket_minimal(self, client):
        resp = await client.post("/v1/tickets", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Support Request"
        assert data["priority"] == "normal"


class TestEntitlements:
    @pytest.mark.asyncio
    async def test_get_entitlements_anonymous(self, client):
        resp = await client.get("/v1/entitlements")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] in ("community", "pro", "enterprise")

    @pytest.mark.asyncio
    async def test_get_entitlements_with_auth(self, client):
        resp = await client.get(
            "/v1/entitlements",
            headers={"Authorization": "Bearer testuser"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # With FLOXBOT_TIER_OVERRIDE=pro set in conftest
        assert data["tier"] == "pro"
