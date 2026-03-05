"""FloxHub auth middleware — authenticates incoming requests."""

from __future__ import annotations

import logging
import os
from typing import Any

from ..models.types import AuthResult

logger = logging.getLogger(__name__)


async def verify_auth(user_identity: dict[str, Any]) -> AuthResult:
    """Verify authentication via FloxHub CLI auth state or dev token.

    Priority:
    1. FloxHub username provided in message (from CLI reading ~/.flox/)
    2. Dev token match (FLOXBOT_DEV_TOKEN env var)
    3. Anonymous / community user
    """
    floxhub_username = user_identity.get("floxhub_username")
    canonical_user_id = user_identity.get("canonical_user_id")

    # If the client already provided a FloxHub username, trust it
    # (The CLI adapter reads this from ~/.flox/ auth files)
    if floxhub_username:
        cid = canonical_user_id or f"usr_{floxhub_username}"
        return AuthResult(
            authenticated=True,
            floxhub_username=floxhub_username,
            canonical_user_id=cid,
        )

    # Check for dev token auth
    from src.config import settings
    dev_token = settings.DEV_TOKEN
    provided_token = user_identity.get("token", "")
    if dev_token and provided_token and provided_token == dev_token:
        cid = canonical_user_id or "usr_dev"
        return AuthResult(
            authenticated=True,
            floxhub_username="dev_user",
            canonical_user_id=cid,
        )

    # If we have a canonical_user_id but no FloxHub username, still partially authenticated
    if canonical_user_id:
        return AuthResult(
            authenticated=True,
            canonical_user_id=canonical_user_id,
        )

    # Anonymous / community user — still allowed, just rate-limited
    return AuthResult(authenticated=False)
