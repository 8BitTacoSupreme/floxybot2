"""Co-Pilot diagnose mode — environment analysis (Pro/Enterprise)."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def run(args):
    """Run diagnose mode (sync entry point)."""
    asyncio.run(async_diagnose(
        api_url=args.api_url,
        offline=getattr(args, "offline", False),
    ))


async def async_diagnose(api_url: str = "http://localhost:8000", offline: bool = False) -> dict[str, Any]:
    """Analyze the current Flox environment and provide a diagnostic report."""
    from ..api_client import CopilotAPIClient
    from ..local.config import get_data_dir, is_offline

    # Gather environment data
    env_data = _gather_environment_data()

    if not env_data["has_flox_env"]:
        msg = "No Flox environment detected in current directory.\nRun 'flox init' to create one."
        print(msg)
        return {"status": "no_env", "message": msg}

    force_offline = offline or is_offline()

    # Try API for enriched analysis
    if not force_offline:
        try:
            client = CopilotAPIClient(api_url=api_url)
            message = _build_diagnostic_message(env_data)
            response = await client.post_message(message)
            await client.close()

            report = _format_report(env_data, response.get("text", ""))
            print(report)
            return {"status": "ok", "report": report}
        except Exception as e:
            logger.warning("API unavailable for diagnosis: %s", e)

    # Offline: basic local analysis
    report = _local_analysis(env_data)
    print(report)
    return {"status": "offline", "report": report}


def _gather_environment_data() -> dict[str, Any]:
    """Read manifest, run flox list, run flox status."""
    data: dict[str, Any] = {
        "has_flox_env": False,
        "manifest": None,
        "packages": [],
        "flox_status": "",
    }

    manifest_path = Path.cwd() / ".flox" / "env" / "manifest.toml"
    if not manifest_path.exists():
        return data

    data["has_flox_env"] = True
    data["manifest"] = manifest_path.read_text()

    # Run flox list
    try:
        result = subprocess.run(
            ["flox", "list"], capture_output=True, text=True, timeout=10
        )
        data["packages"] = result.stdout.strip().split("\n") if result.stdout.strip() else []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        data["packages"] = []

    # Run flox status
    try:
        result = subprocess.run(
            ["flox", "status"], capture_output=True, text=True, timeout=10
        )
        data["flox_status"] = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        data["flox_status"] = "(flox not available)"

    return data


def _build_diagnostic_message(env_data: dict[str, Any]) -> dict[str, Any]:
    """Build a normalized message with diagnostic context."""
    text_parts = ["Please analyze this Flox environment and provide a diagnostic report."]
    if env_data.get("packages"):
        text_parts.append(f"\nInstalled packages: {', '.join(env_data['packages'])}")
    if env_data.get("flox_status"):
        text_parts.append(f"\nFlox status:\n{env_data['flox_status']}")

    return {
        "message_id": str(uuid.uuid4()),
        "user_identity": {
            "channel": "copilot",
            "channel_user_id": "",
            "email": "",
            "canonical_user_id": "",
            "floxhub_username": "",
            "entitlement_tier": "pro",
        },
        "content": {
            "text": "\n".join(text_parts),
            "attachments": [],
            "code_blocks": [{"language": "toml", "content": env_data.get("manifest", "")}] if env_data.get("manifest") else [],
        },
        "context": {
            "project": {
                "has_flox_env": True,
                "manifest": env_data.get("manifest", ""),
                "detected_skills": [],
            },
            "conversation_id": "",
            "channel_metadata": {"mode": "diagnose"},
        },
        "session": {
            "prior_messages": 0,
            "active_skills": [],
            "escalation_attempts": 0,
            "copilot_active": True,
        },
    }


def _format_report(env_data: dict[str, Any], analysis: str) -> str:
    """Format the diagnostic report."""
    lines = [
        "=== FloxBot Environment Diagnostic ===\n",
        f"Flox Environment: {'Active' if env_data['has_flox_env'] else 'Not found'}",
        f"Packages: {len(env_data.get('packages', []))}",
    ]
    if env_data.get("flox_status"):
        lines.append(f"\nStatus:\n{env_data['flox_status']}")
    if analysis:
        lines.append(f"\n--- Analysis ---\n{analysis}")
    return "\n".join(lines)


def _local_analysis(env_data: dict[str, Any]) -> str:
    """Basic offline analysis without API."""
    lines = [
        "=== FloxBot Environment Diagnostic (Offline) ===\n",
        f"Flox Environment: Active",
        f"Packages: {len(env_data.get('packages', []))}",
    ]
    if env_data.get("packages"):
        lines.append("\nInstalled:")
        for pkg in env_data["packages"]:
            lines.append(f"  - {pkg}")

    # Basic checks
    manifest = env_data.get("manifest", "")
    issues = []
    if "[install]" not in manifest and "[options]" not in manifest:
        issues.append("- Manifest appears empty (no [install] or [options] section)")
    if issues:
        lines.append("\nPotential issues:")
        lines.extend(issues)
    else:
        lines.append("\nNo obvious issues detected.")

    lines.append("\nRun online for full AI-powered analysis.")
    return "\n".join(lines)
