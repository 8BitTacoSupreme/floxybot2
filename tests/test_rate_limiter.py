"""Tests for the Redis sliding window rate limiter."""

from __future__ import annotations

import pytest
import pytest_asyncio
import fakeredis.aioredis

from src.auth.rate_limiter import check_rate_limit, rate_limit_headers


@pytest_asyncio.fixture
async def redis():
    r = fakeredis.aioredis.FakeRedis()
    yield r
    await r.aclose()


class TestCheckRateLimit:
    @pytest.mark.asyncio
    async def test_allows_within_limit(self, redis):
        allowed, remaining = await check_rate_limit("user1", 10, redis)
        assert allowed is True
        assert remaining == 9

    @pytest.mark.asyncio
    async def test_decrements_remaining(self, redis):
        for i in range(5):
            allowed, remaining = await check_rate_limit("user1", 10, redis)
            assert allowed is True
        # 5 requests made, 10 limit → 5 remaining
        assert remaining == 5

    @pytest.mark.asyncio
    async def test_blocks_at_limit(self, redis):
        for _ in range(10):
            await check_rate_limit("user1", 10, redis)
        allowed, remaining = await check_rate_limit("user1", 10, redis)
        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_per_user_isolation(self, redis):
        for _ in range(10):
            await check_rate_limit("user1", 10, redis)
        # user2 should still be allowed
        allowed, remaining = await check_rate_limit("user2", 10, redis)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_community_tier_limit(self, redis):
        """Community tier: 10 RPM."""
        for _ in range(10):
            await check_rate_limit("user1", 10, redis)
        allowed, _ = await check_rate_limit("user1", 10, redis)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_pro_tier_limit(self, redis):
        """Pro tier: 60 RPM."""
        for _ in range(60):
            await check_rate_limit("user1", 60, redis)
        allowed, _ = await check_rate_limit("user1", 60, redis)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_redis_none_allows_through(self):
        """Falls through if Redis unavailable."""
        allowed, remaining = await check_rate_limit("user1", 10, None)
        assert allowed is True
        assert remaining == 10

    @pytest.mark.asyncio
    async def test_redis_error_allows_through(self):
        """Falls through if Redis raises."""

        class BrokenRedis:
            def pipeline(self):
                raise ConnectionError("Redis down")

        allowed, remaining = await check_rate_limit("user1", 10, BrokenRedis())
        assert allowed is True
        assert remaining == 10


class TestRateLimitHeaders:
    def test_allowed_headers(self):
        headers = rate_limit_headers(True, 5, 10)
        assert headers["X-RateLimit-Limit"] == "10"
        assert headers["X-RateLimit-Remaining"] == "5"
        assert "Retry-After" not in headers

    def test_denied_headers(self):
        headers = rate_limit_headers(False, 0, 10)
        assert headers["Retry-After"] == "60"
        assert headers["X-RateLimit-Remaining"] == "0"
