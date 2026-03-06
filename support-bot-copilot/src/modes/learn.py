"""Co-Pilot learn mode — guided growth paths (Pro/Enterprise)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def run(args):
    """Run learn mode (sync entry point)."""
    topic = " ".join(args.args) if args.args else None
    asyncio.run(async_learn(
        topic=topic,
        api_url=args.api_url,
        offline=getattr(args, "offline", False),
    ))


async def async_learn(
    topic: str | None = None,
    api_url: str = "http://localhost:8000",
    offline: bool = False,
) -> str:
    """Guided learning session based on user skill level."""
    from ..api_client import CopilotAPIClient
    from ..local.config import get_data_dir, is_offline
    from ..local.sqlite_store import SQLiteStore

    data_dir = get_data_dir()
    force_offline = offline or is_offline()

    # Load local user memory for skill context
    sqlite = SQLiteStore(data_dir / "copilot.db")
    await sqlite.init()
    skill_level = await sqlite.get_memory("skill_level") or "beginner"
    past_topics = await sqlite.get_memory("learn_topics") or []

    if not topic:
        topic = _suggest_topic(skill_level, past_topics)
        print(f"Suggested topic: {topic}")
        try:
            user_topic = input("Topic (press Enter to accept): ").strip()
        except (EOFError, KeyboardInterrupt):
            await sqlite.close()
            return ""
        if user_topic:
            topic = user_topic

    if not force_offline:
        try:
            client = CopilotAPIClient(api_url=api_url)

            # Fetch remote memory for skill context
            try:
                memory = await client.get_memory("local_user")
                if memory.get("skill_level"):
                    skill_level = memory["skill_level"]
            except Exception:
                pass

            message = _build_learn_message(topic, skill_level)
            response = await client.post_message(message)
            await client.close()

            lesson = response.get("text", "No lesson content available.")
            print(f"\n=== Learning: {topic} ===\n")
            print(lesson)
            print()

            # Update progress
            if topic not in past_topics:
                past_topics.append(topic)
                await sqlite.set_memory("learn_topics", past_topics)

            await sqlite.close()
            return lesson
        except Exception as e:
            logger.warning("API unavailable for learn mode: %s", e)

    # Offline fallback
    msg = f"Learn mode requires API connectivity for '{topic}'.\nRun 'copilot-sync' and try again when online."
    print(msg)
    await sqlite.close()
    return msg


def _suggest_topic(skill_level: str, past_topics: list[str]) -> str:
    """Suggest a learning topic based on skill level."""
    beginner_topics = [
        "Getting started with Flox environments",
        "Installing packages with Flox",
        "Flox manifest basics",
        "Sharing environments with FloxHub",
    ]
    intermediate_topics = [
        "Advanced manifest configuration",
        "Flox hooks and services",
        "Multi-environment workflows",
        "Building packages with Flox",
    ]
    advanced_topics = [
        "Custom package derivations",
        "Flox in CI/CD pipelines",
        "Composable environments",
        "Contributing to Flox catalog",
    ]

    if skill_level == "advanced":
        pool = advanced_topics
    elif skill_level == "intermediate":
        pool = intermediate_topics
    else:
        pool = beginner_topics

    for topic in pool:
        if topic not in past_topics:
            return topic
    return pool[0]


def _build_learn_message(topic: str, skill_level: str) -> dict[str, Any]:
    """Build a teaching-oriented message for the API."""
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
            "text": f"Teach me about: {topic}\n\nMy skill level: {skill_level}. "
                    f"Provide a structured lesson with examples.",
            "attachments": [],
            "code_blocks": [],
        },
        "context": {
            "project": {"has_flox_env": False, "manifest": None, "detected_skills": []},
            "conversation_id": "",
            "channel_metadata": {"mode": "learn"},
        },
        "session": {
            "prior_messages": 0,
            "active_skills": [],
            "escalation_attempts": 0,
            "copilot_active": True,
        },
    }
