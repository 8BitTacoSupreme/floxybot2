"""Canon indexing pipeline — embed and index knowledge base documents."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

logger = logging.getLogger(__name__)


async def index_canon(
    source_dir: str,
    db_url: str,
    voyage_api_key: str | None = None,
) -> int:
    """Walk skills directory, chunk documents, embed via Voyage, upsert to pgvector.

    Returns the number of chunks indexed.
    """
    from .chunker import chunk_skill_package
    from .embedder import VoyageEmbedder

    source_path = Path(source_dir)
    if not source_path.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    # Discover skill packages
    skill_dirs = [d for d in sorted(source_path.iterdir()) if d.is_dir()]
    if not skill_dirs:
        logger.warning("No skill directories found in %s", source_dir)
        return 0

    # Chunk all skills
    all_chunks = []
    for skill_dir in skill_dirs:
        chunks = chunk_skill_package(skill_dir)
        if chunks:
            logger.info("Chunked %s: %d chunks", skill_dir.name, len(chunks))
            all_chunks.extend(chunks)

    if not all_chunks:
        logger.warning("No chunks produced from %s", source_dir)
        return 0

    # Embed all chunks
    embedder = VoyageEmbedder(api_key=voyage_api_key)
    texts = [c.content for c in all_chunks]
    logger.info("Embedding %d chunks...", len(texts))
    embeddings = embedder.embed(texts)

    # Upsert to database
    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        # Ensure pgvector extension
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await session.commit()

        count = 0
        for chunk, embedding in zip(all_chunks, embeddings):
            # Use content_hash for idempotent upserts
            stmt = insert(
                _get_canon_table()
            ).values(
                source_file=chunk.source_file,
                skill_name=chunk.skill_name,
                heading_hierarchy=chunk.heading_hierarchy,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                embedding=embedding,
                metadata=chunk.metadata,
                content_hash=chunk.content_hash,
            ).on_conflict_do_update(
                index_elements=["content_hash"],
                set_={
                    "content": chunk.content,
                    "embedding": embedding,
                    "metadata": chunk.metadata,
                    "heading_hierarchy": chunk.heading_hierarchy,
                },
            )
            await session.execute(stmt)
            count += 1

        await session.commit()

    await engine.dispose()
    logger.info("Indexed %d chunks total", count)
    return count


def _get_canon_table():
    """Get the canon_chunks table for raw SQL operations."""
    from src.db.models import CanonChunk
    return CanonChunk.__table__


if __name__ == "__main__":
    import argparse
    import os

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Index canon documents into pgvector")
    parser.add_argument("--source", required=True, help="Skills source directory")
    parser.add_argument(
        "--db-url",
        default=os.environ.get(
            "FLOXBOT_DATABASE_URL",
            "postgresql+asyncpg://floxbot:floxbot@localhost:5432/floxbot",
        ),
        help="Database URL",
    )
    parser.add_argument("--voyage-api-key", default=None, help="Voyage API key")
    args = parser.parse_args()

    count = asyncio.run(index_canon(args.source, args.db_url, args.voyage_api_key))
    print(f"Indexed {count} chunks")
