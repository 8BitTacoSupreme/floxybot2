"""Redis sliding window rate limiter using sorted sets."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


async def check_rate_limit(
    user_id: str,
    tier_rpm: int,
    redis_client: Any | None = None,
) -> tuple[bool, int]:
    """Check if a request is within the rate limit.

    Uses a Redis sorted set sliding window (60s).
    Key: ratelimit:{user_id}
    Score: timestamp, Member: unique request ID (timestamp-based)

    Returns (allowed, remaining). Falls through if Redis unavailable.
    """
    if redis_client is None:
        return True, tier_rpm

    try:
        now = time.time()
        window_start = now - 60.0
        key = f"ratelimit:{user_id}"

        pipe = redis_client.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, window_start)
        # Count current window
        pipe.zcard(key)
        results = await pipe.execute()

        current_count = results[1]

        if current_count >= tier_rpm:
            return False, 0

        # Add this request with a unique member
        member = f"{now}:{uuid.uuid4().hex[:8]}"
        pipe2 = redis_client.pipeline()
        pipe2.zadd(key, {member: now})
        pipe2.expire(key, 120)  # TTL slightly > window
        await pipe2.execute()

        remaining = tier_rpm - current_count - 1
        return True, max(remaining, 0)

    except Exception as e:
        logger.warning("Rate limiter Redis error, allowing through: %s", e)
        return True, tier_rpm


def rate_limit_headers(allowed: bool, remaining: int, rpm: int) -> dict[str, str]:
    """Build rate limit response headers."""
    headers = {
        "X-RateLimit-Limit": str(rpm),
        "X-RateLimit-Remaining": str(remaining),
    }
    if not allowed:
        headers["Retry-After"] = "60"
    return headers
