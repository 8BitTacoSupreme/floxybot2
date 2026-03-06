"""Tests for instance knowledge — embedding-based vote similarity search."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.rag.engine import _score_by_keywords


class TestKeywordFallback:
    """Test keyword-based scoring fallback."""

    def _make_row(self, query_text, response_text, skills_used=None):
        row = MagicMock()
        row.query_text = query_text
        row.response_text = response_text
        row.skills_used = skills_used or {}
        return row

    def test_keyword_overlap_scores(self):
        rows = [
            self._make_row("how to install python", "use flox install python3"),
            self._make_row("how to deploy kubernetes", "use kubectl apply"),
        ]
        scored = _score_by_keywords("install python packages", rows)
        assert len(scored) >= 1
        # "install" and "python" overlap with first row
        assert scored[0][1].query_text == "how to install python"

    def test_no_overlap_returns_empty(self):
        rows = [
            self._make_row("kubernetes deployment", "use kubectl"),
        ]
        scored = _score_by_keywords("python packages", rows)
        assert len(scored) == 0

    def test_empty_query(self):
        rows = [self._make_row("hello", "world")]
        scored = _score_by_keywords("", rows)
        assert len(scored) == 0

    def test_none_fields_skipped(self):
        rows = [
            self._make_row(None, None),
            self._make_row("install python", "flox install python3"),
        ]
        scored = _score_by_keywords("install", rows)
        assert len(scored) == 1

    def test_scores_normalized(self):
        rows = [
            self._make_row("install python flask django", "use pip"),
        ]
        scored = _score_by_keywords("install python", rows)
        assert len(scored) == 1
        score = scored[0][0]
        assert 0.0 < score <= 1.0


class TestInstanceKnowledgeIntegration:
    """Test instance knowledge wired into context engine."""

    def test_built_context_has_instance_knowledge_field(self):
        from src.models.types import BuiltContext
        ctx = BuiltContext()
        assert ctx.instance_knowledge == []

    def test_instance_knowledge_populates(self):
        from src.models.types import BuiltContext
        ctx = BuiltContext(instance_knowledge=[
            {"query": "how to install python", "response": "flox install python3"}
        ])
        assert len(ctx.instance_knowledge) == 1
