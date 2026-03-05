"""Entitlement resolution — maps auth to feature access with Redis caching."""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..models.types import AuthResult, Entitlements

logger = logging.getLogger(__name__)

# Entitlement tier definitions
TIER_CONFIGS = {
    "community": Entitlements(
        tier="community",
        features=["l1_support", "basic_skills", "votes"],
        rate_limit_rpm=10,
        skill_access="basic",
        codex_enabled=False,
        memory_enabled=False,
        copilot_modes=["ask", "chat"],
    ),
    "pro": Entitlements(
        tier="pro",
        features=[
            "l2_support", "full_skills", "votes", "codex",
            "full_memory", "copilot_learn", "copilot_diagnose",
            "copilot_feedback", "copilot_ticket",
        ],
        rate_limit_rpm=60,
        skill_access="full",
        codex_enabled=True,
        memory_enabled=True,
        copilot_modes=["ask", "chat", "diagnose", "learn", "feedback", "ticket"],
    ),
    "enterprise": Entitlements(
        tier="enterprise",
        features=[
            "l2_support", "full_skills", "votes", "codex",
            "full_memory", "custom_skills", "org_knowledge",
            "sso", "admin_dashboard", "sla_routing",
            "copilot_learn", "copilot_diagnose",
            "copilot_feedback", "copilot_ticket",
        ],
        rate_limit_rpm=120,
        skill_access="custom",
        codex_enabled=True,
        memory_enabled=True,
        copilot_modes=["ask", "chat", "diagnose", "learn", "feedback", "ticket"],
    ),
}

# Module-level Redis client (injected via set_redis)
_redis_client = None


def set_redis(redis_client) -> None:
    """Inject Redis client for entitlement caching."""
    global _redis_client
    _redis_client = redis_client


async def resolve_entitlements(
    auth_result: AuthResult,
    redis_client=None,
) -> Entitlements:
    """Resolve entitlements from auth result.

    Cache lookup: Redis key 'entitlements:{user_id}' with 1h TTL.
    Falls back to tier defaults.
    """
    if not auth_result.authenticated:
        return TIER_CONFIGS["community"]

    user_id = auth_result.canonical_user_id or auth_result.floxhub_username
    if not user_id:
        return TIER_CONFIGS["community"]

    rc = redis_client or _redis_client

    # Check Redis cache
    if rc is not None:
        try:
            cache_key = f"entitlements:{user_id}"
            cached = await rc.get(cache_key)
            if cached is not None:
                data = json.loads(cached)
                logger.debug("Cache hit for entitlements:%s", user_id)
                return Entitlements(**data)
        except Exception as e:
            logger.warning("Redis cache read failed: %s", e)

    # Resolve tier (in Phase 1, default to pro for authenticated users)
    # TODO: Query FloxHub API for actual tier
    entitlements = TIER_CONFIGS["pro"]

    # Cache the result
    if rc is not None:
        try:
            from src.config import settings
            cache_key = f"entitlements:{user_id}"
            await rc.set(
                cache_key,
                json.dumps(entitlements.model_dump()),
                ex=settings.ENTITLEMENT_CACHE_TTL,
            )
            logger.debug("Cached entitlements for %s (TTL=%ds)", user_id, settings.ENTITLEMENT_CACHE_TTL)
        except Exception as e:
            logger.warning("Redis cache write failed: %s", e)

    return entitlements
