"""Tests for the canon chunking pipeline."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_chunk_markdown_sections():
    """Splits on headings."""
    from scripts.chunker import chunk_markdown

    md = """# Title

Intro paragraph.

## Section One

Content for section one.

## Section Two

Content for section two.
"""
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write(md)
        f.flush()
        chunks = chunk_markdown(f.name, skill_name="test")

    assert len(chunks) >= 2
    # Each chunk should have content
    for c in chunks:
        assert c.content.strip()
        assert c.skill_name == "test"


def test_chunk_code_blocks_preserved():
    """Code fences are never split mid-block."""
    from scripts.chunker import chunk_markdown

    md = """## Example

Here's some code:

```python
def hello():
    print("Hello, world!")
    print("This is a multi-line code block")
    print("It should never be split")
```

More text after the code.
"""
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write(md)
        f.flush()
        chunks = chunk_markdown(f.name, chunk_size=20, skill_name="test")

    # Find the chunk containing the code block
    code_chunks = [c for c in chunks if "```python" in c.content or "def hello" in c.content]
    assert len(code_chunks) >= 1
    # The code block should be intact
    code_chunk = code_chunks[0]
    assert "def hello():" in code_chunk.content
    assert 'print("It should never be split")' in code_chunk.content


def test_chunk_heading_prefix():
    """Chunks retain heading hierarchy."""
    from scripts.chunker import chunk_markdown

    md = """## Getting Started

Step 1: Do this.

## Advanced Usage

Step 2: Do that.
"""
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write(md)
        f.flush()
        chunks = chunk_markdown(f.name, skill_name="test")

    headings = [c.heading_hierarchy for c in chunks if c.heading_hierarchy]
    assert any("Getting Started" in h for h in headings)
    assert any("Advanced Usage" in h for h in headings)


def test_chunk_skill_package():
    """Indexes SKILL.md + metadata.json from a skill directory."""
    from scripts.chunker import chunk_skill_package

    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir)
        (skill_dir / "SKILL.md").write_text("# My Skill\n\nContent here.\n\n## Details\n\nMore.")
        (skill_dir / "metadata.json").write_text('{"name": "test", "version": "0.1.0"}')

        chunks = chunk_skill_package(skill_dir)

    assert len(chunks) >= 2  # At least SKILL.md chunks + metadata
    skill_names = {c.skill_name for c in chunks}
    assert skill_dir.name in skill_names


def test_chunk_content_hash_unique():
    """Each chunk has a unique content hash."""
    from scripts.chunker import chunk_markdown

    md = """## Section One

Content A.

## Section Two

Content B.
"""
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write(md)
        f.flush()
        chunks = chunk_markdown(f.name, skill_name="test")

    hashes = [c.content_hash for c in chunks]
    assert len(hashes) == len(set(hashes))


def test_chunk_real_core_canon():
    """Chunks the actual core-canon SKILL.md."""
    from scripts.chunker import chunk_skill_package

    skill_dir = Path(__file__).parent.parent / "skills" / "core-canon"
    if not skill_dir.is_dir():
        pytest.skip("core-canon skill not found")

    chunks = chunk_skill_package(skill_dir)
    assert len(chunks) > 0
    assert all(c.skill_name == "core-canon" for c in chunks)
