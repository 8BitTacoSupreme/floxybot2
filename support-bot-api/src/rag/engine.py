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

    # Over-fetch raw results (3x top_k), boost by source type, re-sort, trim
    fetch_limit = top_k * 3

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
            CanonChunk.doc_type,
            CanonChunk.metadata_,
            (1 - distance_expr).label("similarity"),
        )
        .where((1 - distance_expr) >= similarity_threshold)
        .order_by(distance_expr)
        .limit(fetch_limit)
    )

    if skill_names:
        stmt = stmt.where(CanonChunk.skill_name.in_(skill_names))

    result = await session.execute(stmt)
    rows = result.all()

    # Apply source-type boosting (LRM pattern)
    flox_terms = {"flox", "manifest", "activate", "environment", "hook", "service"}
    query_has_flox_terms = bool(set(query.lower().split()) & flox_terms)

    boosted = []
    for row in rows:
        score = float(row.similarity)
        doc_type = row.doc_type or "skill"

        # Tier 1: flox_docs and skill get highest boost
        if doc_type in ("flox_docs", "skill"):
            score *= 1.5
        # Tier 2: blog posts
        elif doc_type == "blog_post":
            score *= 1.3

        # Flox-term bonus for flox_docs
        if query_has_flox_terms and doc_type == "flox_docs":
            score *= 1.2

        score = min(score, 1.0)

        source_label = _source_label(doc_type, row.skill_name)

        boosted.append({
            "id": str(row.id),
            "content": row.content,
            "source_file": row.source_file,
            "skill_name": row.skill_name,
            "heading_hierarchy": row.heading_hierarchy,
            "doc_type": doc_type,
            "metadata": row.metadata_,
            "similarity": score,
            "source_label": source_label,
        })

    boosted.sort(key=lambda r: r["similarity"], reverse=True)
    return boosted[:top_k]


_SOURCE_LABELS = {
    "flox_docs": "Flox Documentation",
    "blog_post": "Flox Blog",
    "nix_docs": "Nix Reference",
    "web_docs": "Flox Documentation",
    "skill": "Skill",
}


def _source_label(doc_type: str, skill_name: str) -> str:
    label = _SOURCE_LABELS.get(doc_type, doc_type.replace("_", " ").title())
    if doc_type == "skill" and skill_name:
        return f"Skill: {skill_name}"
    return label


async def query_instance_knowledge(
    query: str,
    session: AsyncSession,
    org_id: str | None = None,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Query Tier 2 instance knowledge — high-voted Q&A pairs.

    Uses embedding similarity when possible, falls back to keyword matching.
    Ranks by similarity score. Phase 5 will pre-compute vote embeddings.
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
        .limit(50)  # Cap candidates for on-the-fly embedding
    )

    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return []

    # Try embedding-based similarity
    query_embedding = await _embed_query(query)
    if query_embedding is not None:
        scored = await _score_by_embedding(query_embedding, rows)
    else:
        scored = _score_by_keywords(query, rows)

    return [
        {
            "query": row.query_text,
            "response": row.response_text,
            "skills_used": row.skills_used,
            "similarity": score,
            "source": "instance_knowledge",
        }
        for score, row in scored[:top_k]
    ]


async def _score_by_embedding(
    query_embedding: list[float], rows: list
) -> list[tuple[float, Any]]:
    """Score vote Q&A pairs by cosine similarity to query embedding.

    Embeds candidate query texts on-the-fly (acceptable for small sets).
    """
    import numpy as np

    q_vec = np.array(query_embedding)
    q_norm = np.linalg.norm(q_vec)
    if q_norm == 0:
        return _score_by_keywords("", rows)

    candidate_texts = [row.query_text for row in rows if row.query_text]
    if not candidate_texts:
        return []

    # Batch-embed all candidate queries
    try:
        import voyageai
        from src.config import settings

        client = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
        response = client.embed(candidate_texts, model=settings.EMBEDDING_MODEL, input_type="query")
        candidate_embeddings = response.embeddings
    except Exception:
        return _score_by_keywords("", rows)

    scored = []
    for row, c_emb in zip(rows, candidate_embeddings):
        c_vec = np.array(c_emb)
        c_norm = np.linalg.norm(c_vec)
        if c_norm == 0:
            continue
        similarity = float(np.dot(q_vec, c_vec) / (q_norm * c_norm))
        if similarity > 0.3:  # threshold
            scored.append((similarity, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _score_by_keywords(query: str, rows: list) -> list[tuple[float, Any]]:
    """Fallback: score by keyword overlap."""
    query_words = set(query.lower().split())
    scored = []
    for row in rows:
        if not row.query_text or not row.response_text:
            continue
        q_words = set(row.query_text.lower().split())
        overlap = len(query_words & q_words)
        if overlap > 0:
            # Normalize to 0-1 range
            score = overlap / max(len(query_words), 1)
            scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


async def _embed_query(query: str) -> list[float] | None:
    """Embed a query using Voyage AI directly."""
    try:
        import voyageai
        from src.config import settings

        client = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
        response = client.embed([query], model=settings.EMBEDDING_MODEL, input_type="query")
        return response.embeddings[0]
    except Exception as e:
        logger.warning("Failed to embed query: %s", e)
        return None
