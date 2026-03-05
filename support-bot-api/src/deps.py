"""FastAPI dependency injection providers."""

from __future__ import annotations

import logging
from typing import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import get_session_maker
from .events.publisher import EventPublisher, InMemoryPublisher, KafkaPublisher

logger = logging.getLogger(__name__)

# Module-level singletons (set during app startup)
_redis_client = None
_event_publisher: EventPublisher | None = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session for request scope."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_redis():
    """Return the shared Redis client."""
    return _redis_client


async def get_event_publisher() -> EventPublisher:
    """Return the shared event publisher."""
    if _event_publisher is None:
        return InMemoryPublisher()
    return _event_publisher


async def startup() -> None:
    """Initialize shared resources on app startup."""
    global _redis_client, _event_publisher

    from src.config import settings

    # Initialize Redis
    try:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await _redis_client.ping()
        logger.info("Redis connected: %s", settings.REDIS_URL)
    except Exception as e:
        logger.warning("Redis unavailable, entitlement caching disabled: %s", e)
        _redis_client = None

    # Initialize Kafka publisher
    try:
        _event_publisher = KafkaPublisher(settings.KAFKA_BOOTSTRAP)
        logger.info("Kafka publisher initialized: %s", settings.KAFKA_BOOTSTRAP)
    except Exception as e:
        logger.warning("Kafka unavailable, using in-memory publisher: %s", e)
        _event_publisher = InMemoryPublisher()

    # Initialize DB engine
    from .db.engine import get_engine
    get_engine(settings.DATABASE_URL)
    logger.info("Database engine initialized: %s", settings.DATABASE_URL)


async def shutdown() -> None:
    """Cleanup shared resources on app shutdown."""
    global _redis_client, _event_publisher

    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None

    if _event_publisher is not None:
        await _event_publisher.close()
        _event_publisher = None

    from .db.engine import get_engine, reset_engine
    try:
        engine = get_engine()
        await engine.dispose()
    except Exception:
        pass
    reset_engine()
