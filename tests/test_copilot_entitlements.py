"""Tests for Co-Pilot entitlement client."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.entitlements import resolve_local_entitlements, check_mode_access
from src.local.sqlite_store import SQLiteStore


class TestResolveLocalEntitlements:
    @pytest.mark.asyncio
    async def test_api_success_caches(self):
        api_client = AsyncMock()
        api_client.get_entitlements.return_value = {
            "tier": "pro",
            "copilot_modes": ["ask", "chat", "diagnose", "learn", "feedback", "ticket"],
        }
        store = SQLiteStore(":memory:")
        await store.init()

        ent = await resolve_local_entitlements(api_client, store, "user1")
        assert ent["tier"] == "pro"

        # Verify cached
        cached = await store.get_cached_entitlements("user1")
        assert cached["tier"] == "pro"

    @pytest.mark.asyncio
    async def test_api_failure_uses_cache(self):
        api_client = AsyncMock()
        api_client.get_entitlements.side_effect = ConnectionError("offline")
        store = SQLiteStore(":memory:")
        await store.init()
        await store.cache_entitlements("user1", {"tier": "pro", "copilot_modes": ["ask", "chat", "diagnose"]})

        ent = await resolve_local_entitlements(api_client, store, "user1")
        assert ent["tier"] == "pro"

    @pytest.mark.asyncio
    async def test_api_failure_no_cache_defaults_community(self):
        api_client = AsyncMock()
        api_client.get_entitlements.side_effect = ConnectionError("offline")
        store = SQLiteStore(":memory:")
        await store.init()

        ent = await resolve_local_entitlements(api_client, store, "user1")
        assert ent["tier"] == "community"
        assert ent["copilot_modes"] == ["ask", "chat"]


class TestCheckModeAccess:
    def test_ask_always_allowed(self):
        allowed, reason = check_mode_access("ask", {"tier": "community", "copilot_modes": ["ask", "chat"]})
        assert allowed is True

    def test_chat_always_allowed(self):
        allowed, reason = check_mode_access("chat", {"tier": "community", "copilot_modes": ["ask", "chat"]})
        assert allowed is True

    def test_diagnose_requires_pro(self):
        allowed, reason = check_mode_access("diagnose", {"tier": "community", "copilot_modes": ["ask", "chat"]})
        assert allowed is False
        assert "Pro" in reason

    def test_diagnose_allowed_for_pro(self):
        allowed, reason = check_mode_access("diagnose", {
            "tier": "pro",
            "copilot_modes": ["ask", "chat", "diagnose", "learn", "feedback", "ticket"],
        })
        assert allowed is True

    def test_learn_requires_pro(self):
        allowed, _ = check_mode_access("learn", {"tier": "community", "copilot_modes": ["ask", "chat"]})
        assert allowed is False

    def test_feedback_requires_pro(self):
        allowed, _ = check_mode_access("feedback", {"tier": "community", "copilot_modes": ["ask", "chat"]})
        assert allowed is False

    def test_ticket_requires_pro(self):
        allowed, _ = check_mode_access("ticket", {"tier": "community", "copilot_modes": ["ask", "chat"]})
        assert allowed is False

    def test_all_pro_modes_allowed(self):
        ent = {"tier": "pro", "copilot_modes": ["ask", "chat", "diagnose", "learn", "feedback", "ticket"]}
        for mode in ["diagnose", "learn", "feedback", "ticket"]:
            allowed, _ = check_mode_access(mode, ent)
            assert allowed is True, f"{mode} should be allowed for pro"

    def test_unknown_mode(self):
        allowed, reason = check_mode_access("bogus", {"tier": "pro", "copilot_modes": ["ask"]})
        assert allowed is False
        assert "Unknown" in reason
