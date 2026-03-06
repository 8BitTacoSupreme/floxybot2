"""FloxBot Co-Pilot — standalone 1:1 learning and support environment.

Modes: ask, chat, diagnose, learn, feedback, ticket
Local-first: SQLite + ChromaDB for offline canon, JSONL queues for sync.
"""

from __future__ import annotations

import argparse
import asyncio
import sys


MODES = ["ask", "chat", "diagnose", "learn", "feedback", "ticket"]


def main():
    parser = argparse.ArgumentParser(description="FloxBot Co-Pilot")
    parser.add_argument("mode", choices=MODES, help="Co-Pilot mode")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Central API URL")
    parser.add_argument("--offline", action="store_true", help="Force offline mode")
    parser.add_argument("args", nargs="*", help="Mode-specific arguments")

    args = parser.parse_args()

    # Check entitlements for gated modes
    try:
        asyncio.run(_run_with_entitlement_check(args))
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)


async def _run_with_entitlement_check(args):
    """Check entitlements before dispatching to mode handler."""
    from .entitlements import check_mode_access, resolve_local_entitlements
    from .api_client import CopilotAPIClient
    from .local.sqlite_store import SQLiteStore
    from .local.config import get_data_dir

    data_dir = get_data_dir()
    sqlite = SQLiteStore(data_dir / "copilot.db")
    await sqlite.init()

    # Resolve entitlements (best-effort)
    try:
        client = CopilotAPIClient(api_url=args.api_url)
        entitlements = await resolve_local_entitlements(client, sqlite, "local_user")
        await client.close()
    except Exception:
        entitlements = await resolve_local_entitlements(
            type("MockClient", (), {"get_entitlements": staticmethod(lambda: (_ for _ in ()).throw(ConnectionError("offline")))})(),
            sqlite,
            "local_user",
        )

    await sqlite.close()

    # Check mode access
    allowed, reason = check_mode_access(args.mode, entitlements)
    if not allowed:
        print(f"Access denied: {reason}")
        print("Upgrade at https://flox.dev/pricing")
        sys.exit(1)

    # Dispatch to mode handler (await async entry points directly)
    if args.mode == "ask":
        from .modes.ask import async_ask
        question = " ".join(args.args) if args.args else input("Question: ")
        await async_ask(question, api_url=args.api_url, offline=getattr(args, "offline", False))
    elif args.mode == "chat":
        from .modes.chat import async_chat
        await async_chat(api_url=args.api_url, offline=getattr(args, "offline", False))
    elif args.mode == "diagnose":
        from .modes.diagnose import async_diagnose
        await async_diagnose(api_url=args.api_url, offline=getattr(args, "offline", False))
    elif args.mode == "learn":
        from .modes.learn import async_learn
        topic = " ".join(args.args) if args.args else None
        await async_learn(topic=topic, api_url=args.api_url, offline=getattr(args, "offline", False))
    elif args.mode == "feedback":
        from .modes.feedback import async_feedback
        await async_feedback(api_url=args.api_url, offline=getattr(args, "offline", False))
    elif args.mode == "ticket":
        from .modes.ticket import async_ticket
        await async_ticket(api_url=args.api_url, offline=getattr(args, "offline", False))
    else:
        print(f"Unknown mode: {args.mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
