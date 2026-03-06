"""Client-side entitlement checking for Co-Pilot."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Modes requiring Pro+ tier
PRO_MODES = {"diagnose", "learn", "feedback", "ticket"}
COMMUNITY_MODES = {"ask", "chat"}


async def resolve_local_entitlements(api_client, sqlite_store, user_id: str) -> dict[str, Any]:
    """Resolve entitlements, caching locally for offline use.

    1. Try API call
    2. On success, cache in SQLite
    3. On failure, use cached version
    4. If no cache, fall back to community defaults
    """
    try:
        entitlements = await api_client.get_entitlements()
        await sqlite_store.cache_entitlements(user_id, entitlements)
        return entitlements
    except Exception as e:
        logger.warning("Failed to resolve entitlements from API: %s", e)

    # Try cached
    cached = await sqlite_store.get_cached_entitlements(user_id)
    if cached:
        logger.info("Using cached entitlements for %s", user_id)
        return cached

    # Default to community
    logger.info("No cached entitlements, defaulting to community")
    return {
        "tier": "community",
        "features": ["l1_support", "basic_skills", "votes"],
        "rate_limit_rpm": 10,
        "skill_access": "basic",
        "codex_enabled": False,
        "memory_enabled": False,
        "copilot_modes": ["ask", "chat"],
    }


def check_mode_access(mode: str, entitlements: dict[str, Any]) -> tuple[bool, str]:
    """Check if a mode is accessible with the given entitlements.

    Returns (allowed, reason).
    """
    if mode in COMMUNITY_MODES:
        return True, ""

    if mode in PRO_MODES:
        allowed_modes = entitlements.get("copilot_modes", ["ask", "chat"])
        if mode in allowed_modes:
            return True, ""
        tier = entitlements.get("tier", "community")
        return False, f"'{mode}' mode requires Pro or Enterprise tier (current: {tier})"

    return False, f"Unknown mode: {mode}"
