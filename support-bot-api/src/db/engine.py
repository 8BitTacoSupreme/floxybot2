"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine(database_url: str | None = None) -> AsyncEngine:
    """Get or create the async engine (singleton)."""
    global _engine
    if _engine is None:
        if database_url is None:
            from src.config import settings
            database_url = settings.DATABASE_URL
        _engine = create_async_engine(database_url, echo=False, pool_size=10, max_overflow=20)
    return _engine


def get_session_maker(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    """Get or create the session maker (singleton)."""
    global _session_maker
    if _session_maker is None:
        if engine is None:
            engine = get_engine()
        _session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return _session_maker


@asynccontextmanager
async def get_session(
    session_maker: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session with automatic commit/rollback."""
    if session_maker is None:
        session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def reset_engine() -> None:
    """Reset singletons (for testing)."""
    global _engine, _session_maker
    _engine = None
    _session_maker = None
