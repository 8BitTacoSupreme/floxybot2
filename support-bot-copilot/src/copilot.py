"""FloxBot Co-Pilot — standalone 1:1 learning and support environment.

Modes: ask, chat, diagnose, learn, feedback, ticket
Local-first: SQLite + ChromaDB for offline canon, JSONL queues for sync.
"""

from __future__ import annotations

import argparse
import sys


MODES = ["ask", "chat", "diagnose", "learn", "feedback", "ticket"]


def main():
    parser = argparse.ArgumentParser(description="FloxBot Co-Pilot")
    parser.add_argument("mode", choices=MODES, help="Co-Pilot mode")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Central API URL")
    parser.add_argument("--offline", action="store_true", help="Force offline mode")
    parser.add_argument("args", nargs="*", help="Mode-specific arguments")

    args = parser.parse_args()

    # Import mode handler dynamically
    if args.mode == "ask":
        from .modes.ask import run
    elif args.mode == "chat":
        from .modes.chat import run
    elif args.mode == "diagnose":
        from .modes.diagnose import run
    elif args.mode == "learn":
        from .modes.learn import run
    elif args.mode == "feedback":
        from .modes.feedback import run
    elif args.mode == "ticket":
        from .modes.ticket import run
    else:
        parser.print_help()
        sys.exit(1)

    run(args)


if __name__ == "__main__":
    main()
