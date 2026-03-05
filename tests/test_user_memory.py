"""Tests for user memory CRUD — requires PostgreSQL."""

from __future__ import annotations

import pytest


@pytest.mark.db
@pytest.mark.asyncio
async def test_get_memory_not_found(db_session):
    """Non-existent user → empty dict."""
    from src.memory.user import get_user_memory

    result = await get_user_memory("usr_nonexistent", session=db_session)
    assert result == {}


@pytest.mark.db
@pytest.mark.asyncio
async def test_create_memory(db_session):
    """Create new user memory record."""
    from src.memory.user import get_user_memory, update_user_memory

    await update_user_memory(
        "usr_new",
        {
            "skill_level": "intermediate",
            "projects": {"myapp": {"language": "python"}},
            "preferences": {"verbose": True},
        },
        session=db_session,
    )

    result = await get_user_memory("usr_new", session=db_session)
    assert result["skill_level"] == "intermediate"
    assert "myapp" in result["projects"]
    assert result["preferences"]["verbose"] is True


@pytest.mark.db
@pytest.mark.asyncio
async def test_update_memory_merge(db_session):
    """Updating memory merges JSONB fields instead of replacing."""
    from src.memory.user import get_user_memory, update_user_memory

    # Create initial memory
    await update_user_memory(
        "usr_merge",
        {
            "skill_level": "beginner",
            "projects": {"app1": {"lang": "go"}},
        },
        session=db_session,
    )

    # Update with additional project
    await update_user_memory(
        "usr_merge",
        {
            "skill_level": "intermediate",
            "projects": {"app2": {"lang": "python"}},
        },
        session=db_session,
    )

    result = await get_user_memory("usr_merge", session=db_session)
    assert result["skill_level"] == "intermediate"
    assert "app1" in result["projects"]  # Original preserved
    assert "app2" in result["projects"]  # New added


@pytest.mark.db
@pytest.mark.asyncio
async def test_get_memory_no_session():
    """No session → empty dict."""
    from src.memory.user import get_user_memory

    result = await get_user_memory("usr_test", session=None)
    assert result == {}
