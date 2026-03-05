"""Co-Pilot ask mode — single-shot Q&A (all tiers)."""

from __future__ import annotations


def run(args):
    """Run ask mode.

    TODO: Implement with local-first pattern:
    1. Check local canon (SQLite + ChromaDB)
    2. If online, hit Central API for enriched response
    3. Cache result locally
    """
    question = " ".join(args.args) if args.args else input("Question: ")
    print(f"[ask mode placeholder] {question}")
