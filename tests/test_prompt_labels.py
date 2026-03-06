"""Tests for labeled RAG injection in system prompt (T9)."""

from __future__ import annotations

from src.llm.prompts import build_system_prompt
from src.models.types import BuiltContext, SkillPackage


class TestLabeledPrompts:
    """Verify that RAG results appear with source labels and relevance scores."""

    def test_labeled_rag_results_in_prompt(self):
        """RAG results should include [Source Label] and (relevance: NN%)."""
        context = BuiltContext(
            rag_results=[
                {
                    "content": "Use flox activate to enter your environment.",
                    "source_label": "Flox Documentation",
                    "similarity": 0.89,
                    "source_file": "docs/getting-started.md",
                },
                {
                    "content": "Flox 1.4 introduces service management.",
                    "source_label": "Flox Blog",
                    "similarity": 0.74,
                    "source_file": "blogs/flox-1.4.md",
                },
            ]
        )

        prompt = build_system_prompt(context, skills=[], intent="conversational")

        assert "[Flox Documentation] (relevance: 89%)" in prompt
        assert "[Flox Blog] (relevance: 74%)" in prompt
        assert "Use flox activate" in prompt
        assert "service management" in prompt

    def test_fallback_to_source_file_when_no_label(self):
        """If source_label is missing, fall back to source_file."""
        context = BuiltContext(
            rag_results=[
                {
                    "content": "Some content",
                    "source_file": "skills/core-canon/SKILL.md",
                    "similarity": 0.5,
                },
            ]
        )
        prompt = build_system_prompt(context, skills=[], intent="conversational")
        assert "[skills/core-canon/SKILL.md] (relevance: 50%)" in prompt

    def test_empty_rag_no_section(self):
        """No RAG section if no results."""
        context = BuiltContext(rag_results=[])
        prompt = build_system_prompt(context, skills=[], intent="conversational")
        assert "Relevant Knowledge" not in prompt
