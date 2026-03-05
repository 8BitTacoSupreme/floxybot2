"""Read FloxHub CLI auth state from ~/.flox/ config files."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FloxHubAuth:
    username: str
    token: str


def read_floxhub_auth(auth_dir: Path | None = None) -> Optional[FloxHubAuth]:
    """Read FloxHub authentication state from CLI config files.

    Looks for auth credentials in ~/.flox/ directory structure:
    - ~/.flox/floxhub_token (JSON with token + username)
    - ~/.flox/config.toml or similar
    """
    if auth_dir is None:
        from src.config import settings
        auth_dir = settings.FLOXHUB_AUTH_DIR

    if not auth_dir.is_dir():
        logger.debug("FloxHub auth dir not found: %s", auth_dir)
        return None

    # Try JSON token file first
    token_file = auth_dir / "floxhub_token"
    if token_file.is_file():
        try:
            data = json.loads(token_file.read_text())
            token = data.get("token", "")
            username = data.get("username", "")
            if token and username:
                return FloxHubAuth(username=username, token=token)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read FloxHub token file: %s", e)

    # Try flox auth status style (plain text token)
    token_path = auth_dir / "token"
    user_path = auth_dir / "username"
    if token_path.is_file() and user_path.is_file():
        try:
            token = token_path.read_text().strip()
            username = user_path.read_text().strip()
            if token and username:
                return FloxHubAuth(username=username, token=token)
        except OSError as e:
            logger.warning("Failed to read FloxHub auth files: %s", e)

    logger.debug("No valid FloxHub auth found in %s", auth_dir)
    return None
