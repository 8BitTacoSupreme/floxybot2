#!/usr/bin/env python3
"""Multi-source canon ingestion script.

Usage:
    python ingest_docs.py --source-dir /path/to/docs --doc-type flox_docs --skill-name core-canon
    python ingest_docs.py --source-dir /path/to/blogs --doc-type blog_post --skill-name flox-blog

Supported doc_type values: blog_post, flox_docs, nix_docs, web_docs, skill
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from pathlib import Path

# Ensure project root is on path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "support-bot-api"))
sys.path.insert(0, str(project_root / "support-bot-shared"))
sys.path.insert(0, str(project_root / "support-bot-canon"))

from scripts.chunker import chunk_document_directory

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

VALID_DOC_TYPES = {"blog_post", "flox_docs", "nix_docs", "web_docs", "skill"}


def embed_chunks(chunks: list, api_key: str, model: str = "voyage-3-lite", batch_size: int = 32):
    """Embed chunks using Voyage AI. Returns list of (chunk, embedding) pairs."""
    import voyageai

    client = voyageai.Client(api_key=api_key)
    results = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.content for c in batch]
        response = client.embed(texts, model=model, input_type="document")
        for chunk, embedding in zip(batch, response.embeddings):
            results.append((chunk, embedding))
        logger.info("  Embedded %d/%d chunks", min(i + batch_size, len(chunks)), len(chunks))
    return results


def upsert_to_db(embedded_chunks: list, doc_type: str, db_url: str):
    """Upsert embedded chunks to PostgreSQL via SQLAlchemy (sync for simplicity)."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    # Convert async URL to sync
    sync_url = db_url.replace("+asyncpg", "+psycopg2").replace("+aiosqlite", "")
    engine = create_engine(sync_url)

    inserted = 0
    skipped = 0
    with Session(engine) as session:
        for chunk, embedding in embedded_chunks:
            content_hash = chunk.content_hash
            # Check if already exists (dedup by content_hash)
            existing = session.execute(
                text("SELECT id FROM canon_chunks WHERE content_hash = :h"),
                {"h": content_hash},
            ).first()
            if existing:
                skipped += 1
                continue

            session.execute(
                text("""
                    INSERT INTO canon_chunks
                        (id, source_file, skill_name, heading_hierarchy, chunk_index,
                         content, doc_type, embedding, metadata, content_hash, created_at, updated_at)
                    VALUES
                        (gen_random_uuid(), :source_file, :skill_name, :heading, :chunk_index,
                         :content, :doc_type, :embedding, :metadata, :content_hash, now(), now())
                """),
                {
                    "source_file": chunk.source_file,
                    "skill_name": chunk.skill_name,
                    "heading": chunk.heading_hierarchy,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "doc_type": doc_type,
                    "embedding": str(embedding),
                    "metadata": "{}",
                    "content_hash": content_hash,
                },
            )
            inserted += 1

        session.commit()

    logger.info("  Inserted: %d, Skipped (dedup): %d", inserted, skipped)
    return inserted, skipped


def main():
    parser = argparse.ArgumentParser(description="Ingest documents into FloxBot canon")
    parser.add_argument("--source-dir", required=True, help="Directory containing docs to ingest")
    parser.add_argument(
        "--doc-type",
        required=True,
        choices=sorted(VALID_DOC_TYPES),
        help="Document type for classification",
    )
    parser.add_argument("--skill-name", required=True, help="Skill name to assign to chunks")
    parser.add_argument("--db-url", default=None, help="Database URL (default: from env)")
    parser.add_argument("--dry-run", action="store_true", help="Chunk only, don't embed or insert")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        logger.error("Source directory does not exist: %s", source_dir)
        sys.exit(1)

    # 1. Chunk
    logger.info("Chunking documents from: %s", source_dir)
    chunks = chunk_document_directory(source_dir, doc_type=args.doc_type, skill_name=args.skill_name)
    logger.info("  Files processed → %d chunks", len(chunks))

    if not chunks:
        logger.info("No chunks produced. Nothing to do.")
        return

    if args.dry_run:
        logger.info("Dry run complete. %d chunks would be ingested.", len(chunks))
        return

    # 2. Embed
    import os

    api_key = os.environ.get("VOYAGE_API_KEY", "")
    if not api_key:
        logger.error("VOYAGE_API_KEY not set. Cannot embed.")
        sys.exit(1)

    logger.info("Embedding %d chunks via Voyage AI...", len(chunks))
    embedded = embed_chunks(chunks, api_key)

    # 3. Upsert to DB
    db_url = args.db_url or os.environ.get(
        "FLOXBOT_DATABASE_URL",
        "postgresql+asyncpg://floxbot:floxbot@localhost:5432/floxbot",
    )
    logger.info("Upserting to database...")
    inserted, skipped = upsert_to_db(embedded, args.doc_type, db_url)

    logger.info("Done! Total chunks: %d, Inserted: %d, Skipped: %d", len(chunks), inserted, skipped)


if __name__ == "__main__":
    main()
