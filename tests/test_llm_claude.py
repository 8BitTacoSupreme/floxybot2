"""Tests for Claude LLM backend — ALL mocked, zero real API calls."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.prompts import SYSTEM_PROMPT_BASE, build_messages, build_system_prompt
from src.models.types import BuiltContext, SkillPackage


def test_build_system_prompt_base():
    """No skills/RAG — base prompt present."""
    context = BuiltContext()
    prompt = build_system_prompt(context, skills=[], intent="conversational")
    assert "FloxBot" in prompt
    assert "Flox" in prompt


def test_build_system_prompt_with_skills():
    """Skill SKILL.md is injected into prompt."""
    context = BuiltContext()
    skills = [
        SkillPackage(
            name="k8s",
            role="primary",
            skill_md="# Kubernetes\n\nUse kubectl to manage pods.",
        ),
    ]
    prompt = build_system_prompt(context, skills, intent="conversational")
    assert "Kubernetes" in prompt
    assert "Primary Skill: k8s" in prompt


def test_build_system_prompt_with_rag():
    """RAG context is formatted and injected."""
    context = BuiltContext(
        rag_results=[
            {"content": "Use `flox install` to add packages.", "source_file": "core-canon/SKILL.md"},
        ]
    )
    prompt = build_system_prompt(context, skills=[], intent="conversational")
    assert "flox install" in prompt
    assert "Relevant Knowledge" in prompt


def test_build_system_prompt_with_user_memory():
    """User memory context is injected."""
    context = BuiltContext(user_memory={"skill_level": "intermediate", "projects": {"myapp": True}})
    prompt = build_system_prompt(context, skills=[], intent="conversational")
    assert "intermediate" in prompt


def test_build_system_prompt_teaching_intent():
    """Teaching intent adds pedagogical guidance."""
    context = BuiltContext()
    prompt = build_system_prompt(context, skills=[], intent="teaching")
    assert "learn" in prompt.lower() or "explain" in prompt.lower() or "step-by-step" in prompt.lower()


def test_build_messages_simple():
    """Single user message."""
    messages = build_messages("How do I install a package?")
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert "install" in messages[0]["content"]


def test_build_messages_with_code_blocks():
    """Code blocks are appended to user message."""
    messages = build_messages("Fix this", code_blocks=["print('hello')"])
    assert "```" in messages[0]["content"]
    assert "print('hello')" in messages[0]["content"]


def test_build_messages_with_history():
    """History is preserved in order."""
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello! How can I help?"},
    ]
    messages = build_messages("Follow up question", history=history)
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hi"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"
    assert "Follow up" in messages[2]["content"]


@pytest.mark.asyncio
async def test_call_claude_basic(mock_claude):
    """Mocked client returns response, verify shape."""
    from src.llm.claude import call_claude

    message = {
        "message_id": "test-msg-1",
        "content": {"text": "Hello", "code_blocks": []},
    }
    context = BuiltContext()

    result = await call_claude(message, context, skills=[])
    assert result["status"] == "ok"
    assert result["llm_backend"] == "claude"
    assert "text" in result
    assert isinstance(result["code_blocks"], list)


@pytest.mark.asyncio
async def test_call_claude_extracts_code_blocks(mock_claude):
    """Code blocks parsed from markdown response."""
    from src.llm.claude import call_claude

    # Set mock response to include code blocks
    mock_claude._mock_response.content[0].text = (
        "Here's how:\n\n```bash\nflox install python3\n```\n\nThat's it."
    )

    message = {
        "message_id": "test-msg-2",
        "content": {"text": "How do I install Python?", "code_blocks": []},
    }
    context = BuiltContext()

    result = await call_claude(message, context, skills=[])
    assert "flox install python3" in result["code_blocks"][0]


def test_extract_code_blocks():
    """Regex handles various fence formats."""
    from src.llm.claude import extract_code_blocks

    text = """
Here's code:

```python
def foo():
    pass
```

And more:

```
plain code
```

And inline `code` not a block.
"""
    blocks = extract_code_blocks(text)
    assert len(blocks) == 2
    assert "def foo():" in blocks[0]
    assert "plain code" in blocks[1]


def test_estimate_confidence_high_with_rag():
    """High confidence when RAG results are available."""
    from src.llm.claude import estimate_confidence

    context = BuiltContext(
        rag_results=[{"content": "relevant"}],
        skills=[SkillPackage(name="test")],
    )
    score = estimate_confidence("Use flox install to add packages.", context)
    assert score > 0.6


def test_estimate_confidence_low_with_hedging():
    """Low confidence with hedging language."""
    from src.llm.claude import estimate_confidence

    context = BuiltContext()
    score = estimate_confidence("I'm not sure, but I think it might work.", context)
    assert score < 0.5
