"""Shared test fixtures for FloxBot."""

from __future__ import annotations

import os

# Preserve Phase 1 behavior: authenticated users get pro tier
os.environ.setdefault("FLOXBOT_TIER_OVERRIDE", "pro")
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Database fixtures (require a running PostgreSQL with pgvector)
# All function-scoped to share the same event loop as the test coroutine.
# ---------------------------------------------------------------------------

TEST_DB_URL = os.environ.get(
    "FLOXBOT_TEST_DATABASE_URL",
    "postgresql+asyncpg://floxbot:floxbot@localhost:5432/floxbot_test",
)

_tables_created = False


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional session that rolls back after each test."""
    global _tables_created
    engine = create_async_engine(TEST_DB_URL, echo=False)

    if not _tables_created:
        from src.db.models import Base

        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        _tables_created = True

    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.close()
        await trans.rollback()

    await engine.dispose()


@pytest.fixture
def db_session_maker():
    """Return a session maker bound to a test engine."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Mock LLM fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_claude():
    """Patch the Anthropic async client to return a canned response."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="This is a test response from Claude.")]
    mock_response.model = "claude-sonnet-4-6"
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
    mock_response.stop_reason = "end_turn"

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client) as patched:
        patched._mock_client = mock_client
        patched._mock_response = mock_response
        yield patched


@pytest.fixture
def mock_voyage():
    """Patch the Voyage client to return fake embeddings."""
    mock_result = MagicMock()
    # Return 512-dim vectors of zeros (voyage-3-lite dimension)
    mock_result.embeddings = [[0.0] * 512]

    mock_client = MagicMock()
    mock_client.embed = MagicMock(return_value=mock_result)

    with patch("voyageai.Client", return_value=mock_client) as patched:
        patched._mock_client = mock_client
        yield patched


# ---------------------------------------------------------------------------
# Redis fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_redis():
    """Provide a fakeredis async client."""
    r = fakeredis.aioredis.FakeRedis()
    yield r
    await r.aclose()


# ---------------------------------------------------------------------------
# Event publisher fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_publisher():
    """Provide an InMemoryPublisher for testing event publishing."""
    from src.events.publisher import InMemoryPublisher
    return InMemoryPublisher()


# ---------------------------------------------------------------------------
# API client fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def api_client(mock_claude, mock_voyage, mock_redis):
    """Provide a TestClient for the FastAPI app with mocked dependencies."""
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Sample data fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_message() -> dict:
    """A valid NormalizedMessage dict for testing."""
    from tests.factories import make_message
    return make_message()
