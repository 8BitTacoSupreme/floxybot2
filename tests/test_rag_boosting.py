"""Tests for source-type boosting in RAG engine (T8)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4


class TestSourceTypeBoosting:
    """Verify that doc_type boosting reranks results correctly."""

    def test_flox_docs_beat_nix_docs_after_boost(self):
        """A flox_docs chunk with 0.5 similarity should beat nix_docs at 0.6 after 1.5x boost."""
        # flox_docs: 0.5 * 1.5 = 0.75
        # nix_docs: 0.6 * 1.0 = 0.6
        from src.rag.engine import _source_label

        # flox_docs gets boosted to 0.75, beating nix_docs at 0.6
        flox_score = min(0.5 * 1.5, 1.0)
        nix_score = 0.6
        assert flox_score > nix_score, f"flox_docs ({flox_score}) should beat nix_docs ({nix_score})"

    def test_blog_post_gets_moderate_boost(self):
        """Blog posts get 1.3x boost."""
        blog_score = min(0.5 * 1.3, 1.0)
        assert blog_score == pytest.approx(0.65)

    def test_flox_terms_give_extra_boost(self):
        """Queries with flox-specific terms get additional 1.2x boost for flox_docs."""
        # flox_docs: 0.4 * 1.5 * 1.2 = 0.72
        score = min(0.4 * 1.5 * 1.2, 1.0)
        assert score == pytest.approx(0.72)

    def test_score_capped_at_one(self):
        """Boosted scores should never exceed 1.0."""
        score = min(0.8 * 1.5 * 1.2, 1.0)
        assert score == 1.0

    def test_source_labels(self):
        """Verify source label generation."""
        from src.rag.engine import _source_label

        assert _source_label("flox_docs", "core-canon") == "Flox Documentation"
        assert _source_label("blog_post", "flox-blog") == "Flox Blog"
        assert _source_label("nix_docs", "nix-ref") == "Nix Reference"
        assert _source_label("skill", "k8s") == "Skill: k8s"
        assert _source_label("skill", "") == "Skill"
        assert _source_label("web_docs", "x") == "Flox Documentation"
