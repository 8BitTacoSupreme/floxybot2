"""Flox MCP server — tools available to both Claude and Codex backends.

Tools:
- flox_search: Search the Flox catalog
- flox_show: Show package versions
- flox_validate_manifest: Validate a manifest.toml
- flox_list_remote: List packages in a remote environment
- floxhub_env_metadata: Get environment metadata from FloxHub
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


async def flox_search(query: str) -> list[dict[str, Any]]:
    """Search the Flox catalog for packages."""
    try:
        result = subprocess.run(
            ["flox", "search", query, "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.warning("flox search failed: %s", e)
    return []


async def flox_show(package: str) -> dict[str, Any]:
    """Show package details and versions."""
    try:
        result = subprocess.run(
            ["flox", "show", package, "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.warning("flox show failed: %s", e)
    return {}


async def flox_validate_manifest(manifest_content: str) -> dict[str, Any]:
    """Validate a manifest.toml for correctness.

    TODO: Implement via flox edit --check or custom validation.
    """
    return {"valid": True, "errors": []}


async def flox_list_remote(env_ref: str) -> list[dict[str, Any]]:
    """List packages in a remote FloxHub environment."""
    try:
        result = subprocess.run(
            ["flox", "list", "-e", env_ref, "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.warning("flox list remote failed: %s", e)
    return []


async def floxhub_env_metadata(env_ref: str) -> dict[str, Any]:
    """Get environment metadata from FloxHub.

    TODO: Implement via FloxHub API.
    """
    return {}
