"""Tests for RAG engine — pgvector similarity search.

These tests require a running PostgreSQL with pgvector.
They are marked with @pytest.mark.db.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.db.models import CanonChunk, Vote


@pytest.mark.db
@pytest.mark.asyncio
async def test_query_canon_returns_results(db_session):
    """Index chunks, query, verify results returned."""
    # Insert a test chunk with a known embedding
    embedding = [0.1] * 1024
    chunk = CanonChunk(
        source_file="test/SKILL.md",
        skill_name="core-canon",
        heading_hierarchy="## Test",
        content="Use `flox install` to add packages to your environment.",
        embedding=embedding,
        content_hash=f"test_hash_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(chunk)
    await db_session.flush()

    # Mock the Voyage embedder to return a similar vector
    mock_embedder = MagicMock()
    mock_embedder.embed_single.return_value = [0.1] * 1024

    from src.rag.engine import query_canon

    with patch("src.rag.engine._embed_query", return_value=[0.1] * 1024):
        results = await query_canon(
            "how to install a package",
            session=db_session,
            similarity_threshold=0.0,  # Accept all
        )

    assert len(results) > 0
    assert any("flox install" in r["content"] for r in results)


@pytest.mark.db
@pytest.mark.asyncio
async def test_query_canon_skill_filter(db_session):
    """Filter by skill_name works."""
    embedding = [0.2] * 1024
    for skill in ["core-canon", "k8s"]:
        chunk = CanonChunk(
            source_file=f"{skill}/SKILL.md",
            skill_name=skill,
            content=f"Content for {skill}",
            embedding=embedding,
            content_hash=f"filter_{skill}_{uuid.uuid4().hex[:8]}",
        )
        db_session.add(chunk)
    await db_session.flush()

    from src.rag.engine import query_canon

    with patch("src.rag.engine._embed_query", return_value=[0.2] * 1024):
        results = await query_canon(
            "test query",
            session=db_session,
            skill_names=["k8s"],
            similarity_threshold=0.0,
        )

    assert all(r["skill_name"] == "k8s" for r in results)


@pytest.mark.db
@pytest.mark.asyncio
async def test_query_canon_empty_db(db_session):
    """Empty database returns empty list."""
    from src.rag.engine import query_canon

    with patch("src.rag.engine._embed_query", return_value=[0.5] * 1024):
        results = await query_canon("anything", session=db_session, similarity_threshold=0.99)

    assert results == []


@pytest.mark.db
@pytest.mark.asyncio
async def test_query_instance_knowledge_no_votes(db_session):
    """No upvoted pairs → empty."""
    from src.rag.engine import query_instance_knowledge

    results = await query_instance_knowledge("test", session=db_session)
    assert results == []


@pytest.mark.db
@pytest.mark.asyncio
async def test_query_instance_knowledge_with_upvotes(db_session):
    """Upvoted Q&A pairs are returned."""
    vote = Vote(
        message_id=uuid.uuid4(),
        conversation_id="conv_test",
        user_id="usr_test",
        vote="up",
        query_text="How do I install Python?",
        response_text="Use `flox install python3`.",
        skills_used={"core-canon": True},
    )
    db_session.add(vote)
    await db_session.flush()

    from src.rag.engine import query_instance_knowledge

    results = await query_instance_knowledge("install Python", session=db_session)
    assert len(results) > 0
    assert "python3" in results[0]["response"].lower() or "Python" in results[0]["query"]
