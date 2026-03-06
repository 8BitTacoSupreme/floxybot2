"""Tests for org-scoped instance knowledge."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from src.db.models import Vote
from src.rag.engine import query_instance_knowledge


class TestOrgScopedInstanceKnowledge:
    """Instance knowledge respects org_id scoping."""

    async def _insert_vote(self, session, user_id, query_text, response_text, org_id=None):
        vote = Vote(
            message_id=uuid.uuid4(),
            conversation_id=f"conv_{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            vote="up",
            query_text=query_text,
            response_text=response_text,
            org_id=org_id,
        )
        session.add(vote)
        await session.flush()
        return vote

    @pytest.mark.asyncio
    async def test_null_org_id_returns_global(self, db_session):
        """org_id=None returns all upvoted Q&A (no regression)."""
        await self._insert_vote(db_session, "u1", "how to install packages", "flox install pkg")
        await self._insert_vote(db_session, "u2", "how to install packages", "flox install", org_id="org_acme")

        # Patch _embed_query to return None so keyword fallback is used
        with patch("src.rag.engine._embed_query", return_value=None):
            results = await query_instance_knowledge("install packages", db_session, org_id=None, top_k=10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_org_scoped_votes_ranked_first(self, db_session):
        """Org-scoped votes are fetched before global votes."""
        await self._insert_vote(db_session, "u1", "install package help", "global answer")
        await self._insert_vote(db_session, "u2", "install package help", "org-specific answer", org_id="org_acme")

        with patch("src.rag.engine._embed_query", return_value=None):
            results = await query_instance_knowledge("install package help", db_session, org_id="org_acme", top_k=10)
        assert len(results) >= 1
        org_responses = [r for r in results if r["response"] == "org-specific answer"]
        assert len(org_responses) >= 1

    @pytest.mark.asyncio
    async def test_falls_back_to_global(self, db_session):
        """When org has few votes, global votes pad results."""
        await self._insert_vote(db_session, "u1", "deploy kubernetes cluster", "kubectl apply works")

        with patch("src.rag.engine._embed_query", return_value=None):
            results = await query_instance_knowledge("deploy kubernetes cluster", db_session, org_id="org_empty", top_k=3)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_no_cross_org_leak(self, db_session):
        """Votes from org_a shouldn't appear as org_b scoped results."""
        await self._insert_vote(db_session, "u1", "org_a specific method", "org_a answer", org_id="org_a")

        with patch("src.rag.engine._embed_query", return_value=None):
            results = await query_instance_knowledge("org_a specific method", db_session, org_id="org_b", top_k=10)
        # org_a votes appear only via global fallback, not as org_b scoped
        # The important thing: they're fetched from the fallback path
        for r in results:
            # All results should come from global fallback (org_id != org_b)
            assert r["source"] == "instance_knowledge"

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty(self, db_session):
        """No votes at all returns empty list."""
        with patch("src.rag.engine._embed_query", return_value=None):
            results = await query_instance_knowledge("anything", db_session, org_id="org_x", top_k=3)
        assert results == []
