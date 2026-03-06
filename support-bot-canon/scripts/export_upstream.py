"""Weekly anonymized export to upstream canon."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_votes(source_path: str) -> list[dict]:
    """Load vote records from a JSONL file."""
    records = []
    with open(source_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def anonymize(record: dict) -> dict:
    """Strip PII from a vote record.

    - Removes user_id
    - Replaces home directory paths with [PATH]
    - Removes IP addresses
    - Preserves skill names and content
    """
    anon = dict(record)

    # Strip user identifiers
    anon.pop("user_id", None)
    anon.pop("canonical_user_id", None)
    anon.pop("email", None)

    # Replace home directory paths
    home_pattern = re.compile(r"(/Users/[^/\s]+|/home/[^/\s]+)")
    for key in ("query_text", "response_text", "detail"):
        if key in anon and isinstance(anon[key], str):
            anon[key] = home_pattern.sub("[PATH]", anon[key])

    # Remove IP addresses
    ip_pattern = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
    for key in ("query_text", "response_text", "detail"):
        if key in anon and isinstance(anon[key], str):
            anon[key] = ip_pattern.sub("[IP]", anon[key])

    return anon


def _content_hash(record: dict) -> str:
    """Compute a stable content hash for review gate filtering."""
    content = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()


def apply_review_gate(
    records: list[dict],
    approved_ids_path: str | None = None,
) -> list[dict]:
    """Filter records by approved content hashes.

    If approved_ids_path is None, all records pass (no gate).
    Otherwise, only records whose content hash appears in the approval file pass.
    """
    if approved_ids_path is None:
        return records

    approved_path = Path(approved_ids_path)
    if not approved_path.exists():
        logger.warning("Approval file not found: %s — passing all records", approved_ids_path)
        return records

    approved_hashes = set()
    with open(approved_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                approved_hashes.add(line)

    return [r for r in records if _content_hash(r) in approved_hashes]


def export_upstream(
    source_path: str,
    output_path: str,
    approved_ids_path: str | None = None,
):
    """Orchestrate: load → anonymize → gate → write JSON."""
    logger.info("Exporting upstream from %s to %s", source_path, output_path)

    records = load_votes(source_path)
    logger.info("Loaded %d vote records", len(records))

    anonymized = [anonymize(r) for r in records]
    gated = apply_review_gate(anonymized, approved_ids_path)

    logger.info("After review gate: %d records", len(gated))

    with open(output_path, "w") as f:
        json.dump({"records": gated, "count": len(gated)}, f, indent=2, default=str)

    logger.info("Export complete: %s", output_path)
    return gated


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="JSONL vote file")
    parser.add_argument("--output", required=True, help="Output JSON file")
    parser.add_argument("--approved-ids", default=None, help="Approved content hashes file")
    args = parser.parse_args()
    export_upstream(args.source, args.output, args.approved_ids)
