"""Flox MCP server — tools available to both Claude and Codex backends.

Tools:
- flox_search: Search the Flox catalog
- flox_show: Show package versions
- flox_validate_manifest: Validate a manifest.toml
- flox_list_remote: List packages in a remote environment
- floxhub_env_metadata: Get environment metadata from FloxHub
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def _run_flox_command(*args: str, timeout: float = 15.0) -> tuple[int, str, str]:
    """Run a flox CLI command asynchronously. Returns (returncode, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "flox", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, stdout.decode(), stderr.decode()
    except asyncio.TimeoutError:
        logger.warning("flox %s timed out after %.0fs", " ".join(args), timeout)
        try:
            proc.kill()  # type: ignore[possibly-undefined]
        except Exception:
            pass
        return 1, "", "Command timed out"
    except FileNotFoundError:
        logger.warning("flox binary not found")
        return 1, "", "flox binary not found"
    except Exception as e:
        logger.warning("flox %s failed: %s", " ".join(args), e)
        return 1, "", str(e)


async def flox_search(query: str) -> list[dict[str, Any]]:
    """Search the Flox catalog for packages."""
    rc, stdout, stderr = await _run_flox_command("search", query, "--json")
    if rc == 0 and stdout.strip():
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning("Failed to parse flox search output")
    return []


async def flox_show(package: str) -> dict[str, Any]:
    """Show package details and versions."""
    rc, stdout, stderr = await _run_flox_command("show", package, "--json")
    if rc == 0 and stdout.strip():
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning("Failed to parse flox show output")
    return {}


async def flox_validate_manifest(manifest_content: str) -> dict[str, Any]:
    """Validate a manifest.toml for correctness.

    Attempts TOML parse and basic structural validation.
    """
    errors: list[str] = []
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {"valid": True, "errors": [], "note": "TOML parser not available"}

    try:
        parsed = tomllib.loads(manifest_content)
    except Exception as e:
        return {"valid": False, "errors": [f"TOML parse error: {e}"]}

    # Basic structural checks
    if "version" not in parsed:
        errors.append("Missing required 'version' key")
    if "install" in parsed and not isinstance(parsed["install"], dict):
        errors.append("[install] must be a table")

    return {"valid": len(errors) == 0, "errors": errors}


async def flox_list_remote(env_ref: str) -> list[dict[str, Any]]:
    """List packages in a remote FloxHub environment."""
    rc, stdout, stderr = await _run_flox_command("list", "-e", env_ref, "--json")
    if rc == 0 and stdout.strip():
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning("Failed to parse flox list output")
    return []


async def floxhub_env_metadata(env_ref: str) -> dict[str, Any]:
    """Get environment metadata from FloxHub."""
    rc, stdout, stderr = await _run_flox_command("list", "-e", env_ref, "--json")
    if rc == 0 and stdout.strip():
        try:
            packages = json.loads(stdout)
            return {"env_ref": env_ref, "packages": packages}
        except json.JSONDecodeError:
            pass
    return {"env_ref": env_ref, "packages": [], "error": stderr.strip() if stderr else "Unknown error"}
