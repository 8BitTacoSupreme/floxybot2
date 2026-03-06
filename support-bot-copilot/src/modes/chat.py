"""Co-Pilot chat mode — multi-turn conversation (all tiers)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def run(args):
    """Run chat mode (sync entry point)."""
    asyncio.run(async_chat(
        api_url=args.api_url,
        offline=getattr(args, "offline", False),
    ))


async def async_chat(api_url: str = "http://localhost:8000", offline: bool = False) -> None:
    """Multi-turn chat REPL."""
    from ..api_client import CopilotAPIClient
    from ..local.config import get_data_dir, is_offline
    from ..local.sqlite_store import SQLiteStore
    from ..local.chroma_store import ChromaStore
    from ..local.jsonl_queue import JSONLQueue

    data_dir = get_data_dir()
    force_offline = offline or is_offline()
    conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
    messages: list[dict[str, str]] = []

    # Initialize local stores
    sqlite = SQLiteStore(data_dir / "copilot.db")
    await sqlite.init()

    client = None
    if not force_offline:
        try:
            client = CopilotAPIClient(api_url=api_url)
            # Quick health check
            await client.get_entitlements()
        except Exception:
            logger.warning("API unavailable, running in offline mode")
            client = None

    chroma = ChromaStore(persist_dir=str(data_dir / "chroma"))
    vote_queue = JSONLQueue(data_dir / "votes.jsonl")

    print("FloxBot Chat (type /exit to quit, /vote up|down to vote)\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # Handle inline commands
        if user_input == "/exit":
            print("Goodbye!")
            break

        if user_input.startswith("/vote "):
            vote_value = user_input.split(" ", 1)[1].strip()
            if vote_value in ("up", "down"):
                vote_queue.append({
                    "message_id": str(uuid.uuid4()),
                    "conversation_id": conversation_id,
                    "user_id": "",
                    "vote": vote_value,
                })
                print(f"Vote '{vote_value}' recorded locally.")
            else:
                print("Usage: /vote up|down")
            continue

        # Build message with history
        messages.append({"role": "user", "content": user_input})

        response_text = await _get_response(
            user_input, messages, conversation_id, client, chroma
        )

        messages.append({"role": "assistant", "content": response_text})
        print(f"\nFloxBot: {response_text}\n")

        # Save conversation locally
        await sqlite.save_conversation(conversation_id, messages)

    # Cleanup — guard against cancelled event loop on Ctrl+C
    try:
        if client:
            await client.close()
        await sqlite.close()
    except (asyncio.CancelledError, Exception):
        pass


async def _get_response(
    user_input: str,
    messages: list[dict],
    conversation_id: str,
    client,
    chroma,
) -> str:
    """Get response from API or local fallback."""
    if client:
        try:
            message = _build_chat_message(user_input, conversation_id, len(messages) - 1)
            response = await client.post_message(message)
            return response.get("text", "No response.")
        except Exception as e:
            logger.warning("API call failed: %s", e)

    # Offline fallback
    results = chroma.query(user_input, top_k=3)
    if results:
        parts = ["(Offline)"]
        for r in results:
            parts.append(r["document"])
        return "\n".join(parts)

    return "(Offline) No local knowledge available. Run 'copilot-sync' to populate."


def _build_chat_message(text: str, conversation_id: str, prior_messages: int) -> dict[str, Any]:
    """Build a normalized message for the chat API call."""
    from .ask import _detect_project_context

    return {
        "message_id": str(uuid.uuid4()),
        "user_identity": {
            "channel": "copilot",
            "channel_user_id": "",
            "email": "",
            "canonical_user_id": "",
            "floxhub_username": "",
            "entitlement_tier": "community",
        },
        "content": {
            "text": text,
            "attachments": [],
            "code_blocks": [],
        },
        "context": {
            "project": _detect_project_context(),
            "conversation_id": conversation_id,
            "channel_metadata": {},
        },
        "session": {
            "prior_messages": prior_messages,
            "active_skills": [],
            "escalation_attempts": 0,
            "copilot_active": True,
        },
    }
