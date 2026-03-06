"""Co-Pilot configuration — data dir resolution, API URL, offline detection."""

from __future__ import annotations

import json
import os
from pathlib import Path


def get_data_dir() -> Path:
    """Resolve the Co-Pilot data directory.

    Priority: FLOXBOT_COPILOT_DATA_DIR > $FLOX_ENV_CACHE/copilot > ~/.local/share/floxbot-copilot
    """
    explicit = os.environ.get("FLOXBOT_COPILOT_DATA_DIR")
    if explicit:
        p = Path(explicit)
        p.mkdir(parents=True, exist_ok=True)
        return p

    flox_cache = os.environ.get("FLOX_ENV_CACHE")
    if flox_cache:
        p = Path(flox_cache) / "copilot"
        p.mkdir(parents=True, exist_ok=True)
        return p

    p = Path.home() / ".local" / "share" / "floxbot-copilot"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_api_url() -> str:
    """Return the Central API URL."""
    return os.environ.get("FLOXBOT_API_URL", "http://localhost:8000")


def is_offline() -> bool:
    """Check if we're in forced offline mode."""
    return os.environ.get("FLOXBOT_OFFLINE", "").lower() in ("1", "true", "yes")


def read_floxhub_token() -> str | None:
    """Read the FloxHub auth token for API requests."""
    auth_dir = Path(os.environ.get("FLOXHUB_AUTH_DIR", str(Path.home() / ".flox")))

    # Try JSON format
    token_file = auth_dir / "floxhub_token"
    if token_file.exists():
        try:
            data = json.loads(token_file.read_text())
            return data.get("token")
        except (json.JSONDecodeError, KeyError):
            # Maybe plain text
            return token_file.read_text().strip() or None

    # Try separate token file
    token_file = auth_dir / "token"
    if token_file.exists():
        return token_file.read_text().strip() or None

    return None
