"""Tests for context engine."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.models.types import Entitlements


@pytest.mark.asyncio
async def test_build_context_minimal():
    """Minimal message → context with project info only."""
    from src.context.engine import build_context

    message = {
        "content": {"text": "Hello"},
        "context": {
            "project": {"has_flox_env": True, "manifest": "[install]", "detected_skills": []},
        },
        "user_identity": {},
    }
    entitlements = Entitlements()

    context = await build_context(message, entitlements)
    assert context.project_context["has_flox_env"] is True
    assert context.rag_results == []
    assert context.user_memory == {}


@pytest.mark.asyncio
async def test_build_context_no_project():
    """No project context → empty project_context."""
    from src.context.engine import build_context

    message = {"content": {"text": "Hello"}, "context": {}, "user_identity": {}}
    entitlements = Entitlements()

    context = await build_context(message, entitlements)
    assert context.project_context == {}


@pytest.mark.asyncio
async def test_build_context_with_memory_enabled():
    """Memory-enabled entitlement triggers user memory lookup."""
    from src.context.engine import build_context

    message = {
        "content": {"text": "Help me"},
        "context": {},
        "user_identity": {"canonical_user_id": "usr_test"},
    }
    entitlements = Entitlements(memory_enabled=True)

    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    context = await build_context(message, entitlements, session=mock_session)
    # Should have attempted memory lookup (returns empty since user not found)
    assert context.user_memory == {}
