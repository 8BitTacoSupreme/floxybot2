"""RAG engine — retrieval-augmented generation against the canon via pgvector."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import CanonChunk, Vote

logger = logging.getLogger(__name__)


async def query_canon(
    query: str,
    session: AsyncSession,
    skill_names: list[str] | None = None,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Query the canon knowledge base using pgvector cosine similarity search.

    1. Embed the query with Voyage
    2. Run cosine similarity search against canon_chunks
    3. Filter by skill and threshold
    4. Return top_k results
    """
    from src.config import settings

    if top_k is None:
        top_k = settings.RAG_TOP_K
    if similarity_threshold is None:
        similarity_threshold = settings.RAG_SIMILARITY_THRESHOLD

    # Embed the query
    query_embedding = await _embed_query(query)
    if query_embedding is None:
        logger.warning("Failed to embed query, returning empty results")
        return []

    # Build the similarity search query
    # pgvector cosine distance: 1 - (a <=> b) gives cosine similarity
    distance_expr = CanonChunk.embedding.cosine_distance(query_embedding)

    stmt = (
        select(
            CanonChunk.id,
            CanonChunk.content,
            CanonChunk.source_file,
            CanonChunk.skill_name,
            CanonChunk.heading_hierarchy,
            CanonChunk.metadata_,
            (1 - distance_expr).label("similarity"),
        )
        .where((1 - distance_expr) >= similarity_threshold)
        .order_by(distance_expr)
        .limit(top_k)
    )

    if skill_names:
        stmt = stmt.where(CanonChunk.skill_name.in_(skill_names))

    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "id": str(row.id),
            "content": row.content,
            "source_file": row.source_file,
            "skill_name": row.skill_name,
            "heading_hierarchy": row.heading_hierarchy,
            "metadata": row.metadata_,
            "similarity": float(row.similarity),
        }
        for row in rows
    ]


async def query_instance_knowledge(
    query: str,
    session: AsyncSession,
    org_id: str | None = None,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Query Tier 2 instance knowledge — high-voted Q&A pairs.

    Finds upvoted responses that match the query topic.
    """
    # Get highly-upvoted Q&A pairs
    stmt = (
        select(
            Vote.query_text,
            Vote.response_text,
            Vote.skills_used,
        )
        .where(Vote.vote == "up")
        .where(Vote.query_text.isnot(None))
        .where(Vote.response_text.isnot(None))
        .order_by(Vote.created_at.desc())
        .limit(top_k * 3)  # Over-fetch, then filter
    )

    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return []

    # Simple keyword matching for now (will be replaced with embedding search)
    query_words = set(query.lower().split())
    scored = []
    for row in rows:
        if not row.query_text or not row.response_text:
            continue
        q_words = set(row.query_text.lower().split())
        overlap = len(query_words & q_words)
        if overlap > 0:
            scored.append((overlap, row))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "query": row.query_text,
            "response": row.response_text,
            "skills_used": row.skills_used,
            "source": "instance_knowledge",
        }
        for _, row in scored[:top_k]
    ]


async def _embed_query(query: str) -> list[float] | None:
    """Embed a query using Voyage AI."""
    try:
        from scripts.embedder import VoyageEmbedder
        embedder = VoyageEmbedder()
        return embedder.embed_single(query)
    except Exception as e:
        logger.warning("Failed to embed query: %s", e)
        return None
