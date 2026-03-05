"""Tests for auth middleware and entitlement resolution."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_verify_auth_anonymous():
    """No identity → unauthenticated."""
    from src.auth.middleware import verify_auth

    result = await verify_auth({})
    assert result.authenticated is False
    assert result.floxhub_username is None


@pytest.mark.asyncio
async def test_verify_auth_with_floxhub_username():
    """FloxHub username provided → authenticated."""
    from src.auth.middleware import verify_auth

    result = await verify_auth({"floxhub_username": "alice"})
    assert result.authenticated is True
    assert result.floxhub_username == "alice"
    assert result.canonical_user_id == "usr_alice"


@pytest.mark.asyncio
async def test_verify_auth_with_dev_token():
    """Matching dev token → authenticated."""
    from src.auth.middleware import verify_auth

    with patch("src.config.settings.DEV_TOKEN", "secret123"):
        result = await verify_auth({"token": "secret123"})
    assert result.authenticated is True
    assert result.floxhub_username == "dev_user"


@pytest.mark.asyncio
async def test_verify_auth_dev_token_mismatch():
    """Non-matching dev token → unauthenticated."""
    from src.auth.middleware import verify_auth

    with patch("src.config.settings.DEV_TOKEN", "secret123"):
        result = await verify_auth({"token": "wrong"})
    assert result.authenticated is False


@pytest.mark.asyncio
async def test_verify_auth_canonical_user_id_only():
    """canonical_user_id without username → partially authenticated."""
    from src.auth.middleware import verify_auth

    result = await verify_auth({"canonical_user_id": "usr_bob"})
    assert result.authenticated is True
    assert result.canonical_user_id == "usr_bob"
    assert result.floxhub_username is None


def test_read_floxhub_auth_missing_dir():
    """Missing auth dir → None."""
    from src.auth.floxhub import read_floxhub_auth

    result = read_floxhub_auth(Path("/nonexistent"))
    assert result is None


def test_read_floxhub_auth_json_token():
    """JSON token file → extracts username + token."""
    from src.auth.floxhub import read_floxhub_auth

    with tempfile.TemporaryDirectory() as tmpdir:
        auth_dir = Path(tmpdir)
        token_file = auth_dir / "floxhub_token"
        token_file.write_text(json.dumps({"username": "alice", "token": "tok123"}))

        result = read_floxhub_auth(auth_dir)
        assert result is not None
        assert result.username == "alice"
        assert result.token == "tok123"


def test_read_floxhub_auth_separate_files():
    """Separate token + username files → extracts both."""
    from src.auth.floxhub import read_floxhub_auth

    with tempfile.TemporaryDirectory() as tmpdir:
        auth_dir = Path(tmpdir)
        (auth_dir / "token").write_text("tok456")
        (auth_dir / "username").write_text("bob")

        result = read_floxhub_auth(auth_dir)
        assert result is not None
        assert result.username == "bob"
        assert result.token == "tok456"


# --- Entitlement tests ---


@pytest.mark.asyncio
async def test_resolve_entitlements_community():
    """Unauthenticated → community tier."""
    from src.auth.entitlements import resolve_entitlements
    from src.models.types import AuthResult

    result = await resolve_entitlements(AuthResult(authenticated=False))
    assert result.tier == "community"
    assert result.codex_enabled is False


@pytest.mark.asyncio
async def test_resolve_entitlements_authenticated():
    """Authenticated → pro tier (Phase 1 default)."""
    from src.auth.entitlements import resolve_entitlements
    from src.models.types import AuthResult

    result = await resolve_entitlements(
        AuthResult(authenticated=True, canonical_user_id="usr_test")
    )
    assert result.tier == "pro"
    assert result.codex_enabled is True


@pytest.mark.asyncio
async def test_resolve_entitlements_cached(mock_redis):
    """Second call reads from Redis cache."""
    from src.auth.entitlements import resolve_entitlements
    from src.models.types import AuthResult

    auth = AuthResult(authenticated=True, canonical_user_id="usr_cached")

    # First call — caches
    result1 = await resolve_entitlements(auth, redis_client=mock_redis)
    assert result1.tier == "pro"

    # Verify it's in Redis
    cached = await mock_redis.get("entitlements:usr_cached")
    assert cached is not None

    # Second call — reads from cache
    result2 = await resolve_entitlements(auth, redis_client=mock_redis)
    assert result2.tier == "pro"


@pytest.mark.asyncio
async def test_resolve_entitlements_cache_ttl(mock_redis):
    """Expired entry triggers re-resolution."""
    from src.auth.entitlements import resolve_entitlements
    from src.models.types import AuthResult

    auth = AuthResult(authenticated=True, canonical_user_id="usr_ttl")

    # First call caches
    await resolve_entitlements(auth, redis_client=mock_redis)

    # Delete from Redis to simulate expiry
    await mock_redis.delete("entitlements:usr_ttl")

    # Should still resolve (just re-caches)
    result = await resolve_entitlements(auth, redis_client=mock_redis)
    assert result.tier == "pro"
