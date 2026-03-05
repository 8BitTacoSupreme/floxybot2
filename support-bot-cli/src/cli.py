"""FloxBot CLI — lightweight ask/chat interface."""

from __future__ import annotations

import argparse
import json
import sys
from uuid import uuid4

import httpx


DEFAULT_API_URL = "http://localhost:8000"


def build_message(text: str, conversation_id: str | None = None) -> dict:
    """Build a normalized message from CLI input."""
    return {
        "message_id": str(uuid4()),
        "user_identity": {
            "channel": "cli",
            "channel_user_id": "cli_user",
            "floxhub_username": None,  # TODO: Read from flox auth
            "entitlement_tier": "community",
        },
        "content": {
            "text": text,
            "attachments": [],
            "code_blocks": [],
        },
        "context": {
            "project": detect_project_context(),
            "conversation_id": conversation_id,
            "channel_metadata": {},
        },
        "session": {
            "prior_messages": 0,
            "active_skills": [],
            "escalation_attempts": 0,
            "copilot_active": False,
        },
    }


def detect_project_context() -> dict:
    """Detect Flox project context from current directory.

    TODO: Read .flox/env/manifest.toml if present, detect skills.
    """
    from pathlib import Path

    manifest_path = Path(".flox/env/manifest.toml")
    if manifest_path.exists():
        return {
            "has_flox_env": True,
            "manifest": manifest_path.read_text(),
            "detected_skills": [],
        }
    return {"has_flox_env": False, "manifest": None, "detected_skills": []}


def ask(question: str, api_url: str = DEFAULT_API_URL) -> str:
    """Single-shot question."""
    message = build_message(question)
    response = httpx.post(f"{api_url}/v1/message", json=message, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("text", "No response")


def chat(api_url: str = DEFAULT_API_URL) -> None:
    """Multi-turn conversation."""
    conversation_id = f"conv_{uuid4().hex[:12]}"
    prior_messages = 0

    print("FloxBot Chat (type 'exit' to quit)")
    print("-" * 40)

    while True:
        try:
            user_input = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break

        if not user_input:
            continue

        message = build_message(user_input, conversation_id)
        message["session"]["prior_messages"] = prior_messages

        try:
            response = httpx.post(f"{api_url}/v1/message", json=message, timeout=30)
            response.raise_for_status()
            data = response.json()
            print(f"\nbot> {data.get('text', 'No response')}")
            prior_messages += 2  # user + bot
        except httpx.HTTPError as e:
            print(f"\n[error] {e}")


def main():
    parser = argparse.ArgumentParser(description="FloxBot CLI")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Central API URL")
    sub = parser.add_subparsers(dest="command")

    ask_parser = sub.add_parser("ask", help="Single-shot question")
    ask_parser.add_argument("question", nargs="+", help="Your question")

    sub.add_parser("chat", help="Multi-turn conversation")

    args = parser.parse_args()

    if args.command == "ask":
        answer = ask(" ".join(args.question), args.api_url)
        print(answer)
    elif args.command == "chat":
        chat(args.api_url)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
