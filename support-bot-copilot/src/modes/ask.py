"""Co-Pilot ask mode — single-shot Q&A (all tiers)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def run(args):
    """Run ask mode (sync entry point)."""
    question = " ".join(args.args) if args.args else input("Question: ")
    if not question.strip():
        print("No question provided.")
        return

    asyncio.run(async_ask(
        question,
        api_url=args.api_url,
        offline=getattr(args, "offline", False),
    ))


async def async_ask(question: str, api_url: str = "http://localhost:8000", offline: bool = False) -> str:
    """Async ask implementation. Returns the answer text."""
    from ..api_client import CopilotAPIClient
    from ..local.config import get_data_dir, is_offline
    from ..local.sqlite_store import SQLiteStore
    from ..local.chroma_store import ChromaStore
    from ..local.jsonl_queue import JSONLQueue

    data_dir = get_data_dir()
    force_offline = offline or is_offline()

    # Try online first
    if not force_offline:
        try:
            client = CopilotAPIClient(api_url=api_url)
            message = _build_message(question)
            response = await client.post_message(message)
            await client.close()

            answer = response.get("text", "No response received.")
            print(f"\n{answer}\n")

            # Prompt for vote
            await _prompt_vote(response, data_dir)

            return answer
        except Exception as e:
            logger.warning("API unavailable, falling back to offline: %s", e)

    # Offline: query local ChromaDB
    chroma = ChromaStore(persist_dir=str(data_dir / "chroma"))
    results = chroma.query(question, top_k=3)

    if not results:
        msg = "No local knowledge available. Run 'copilot-sync' to populate local cache."
        print(f"\n{msg}\n")
        return msg

    # Format best results
    answer_parts = ["(Offline — from local knowledge base)\n"]
    for r in results:
        meta = r.get("metadata", {})
        skill = meta.get("skill_name", "")
        heading = meta.get("heading", "")
        prefix = f"[{skill}]" if skill else ""
        if heading:
            prefix += f" {heading}"
        if prefix:
            answer_parts.append(f"**{prefix.strip()}**")
        answer_parts.append(r["document"])
        answer_parts.append("")

    answer = "\n".join(answer_parts)
    print(f"\n{answer}")
    return answer


async def _prompt_vote(response: dict[str, Any], data_dir: Path) -> None:
    """Prompt user for vote on the response."""
    try:
        vote_input = input("Was this helpful? (y/n/skip): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return

    if vote_input in ("y", "n"):
        from ..local.jsonl_queue import JSONLQueue
        queue = JSONLQueue(data_dir / "votes.jsonl")
        queue.append({
            "message_id": response.get("message_id", str(uuid.uuid4())),
            "conversation_id": response.get("conversation_id", ""),
            "user_id": response.get("user_id", ""),
            "vote": "up" if vote_input == "y" else "down",
        })
        print("Vote recorded locally.")


def _build_message(question: str) -> dict[str, Any]:
    """Build a normalized message for the API."""
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
            "text": question,
            "attachments": [],
            "code_blocks": [],
        },
        "context": {
            "project": _detect_project_context(),
            "conversation_id": "",
            "channel_metadata": {},
        },
        "session": {
            "prior_messages": 0,
            "active_skills": [],
            "escalation_attempts": 0,
            "copilot_active": True,
        },
    }


def _detect_project_context() -> dict[str, Any]:
    """Detect Flox project context in CWD."""
    manifest = Path.cwd() / ".flox" / "env" / "manifest.toml"
    if manifest.exists():
        return {
            "has_flox_env": True,
            "manifest": manifest.read_text(),
            "detected_skills": [],
        }
    return {
        "has_flox_env": False,
        "manifest": None,
        "detected_skills": [],
    }
