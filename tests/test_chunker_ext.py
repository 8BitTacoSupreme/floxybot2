"""Tests for extended chunker — chunk_document_directory (T4)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from scripts.chunker import chunk_document_directory


class TestChunkDocumentDirectory:
    """Verify recursive directory chunking."""

    def test_chunks_markdown_files(self, tmp_path: Path):
        """Should find and chunk .md files recursively."""
        (tmp_path / "doc1.md").write_text("# Hello\n\nThis is a test document about Flox.")
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "doc2.md").write_text("## Nested\n\nMore content here.")

        chunks = chunk_document_directory(tmp_path, doc_type="flox_docs", skill_name="test-skill")

        assert len(chunks) >= 2
        assert all(c.skill_name == "test-skill" for c in chunks)
        assert all(c.metadata.get("doc_type") == "flox_docs" for c in chunks)

    def test_chunks_html_files(self, tmp_path: Path):
        """Should strip HTML tags and chunk."""
        (tmp_path / "page.html").write_text(
            "<html><body><h1>Title</h1><p>This is HTML content about environments.</p></body></html>"
        )

        chunks = chunk_document_directory(tmp_path, doc_type="web_docs", skill_name="core-canon")

        assert len(chunks) >= 1
        # Should contain stripped text, not tags
        assert "<html>" not in chunks[0].content
        assert "environments" in chunks[0].content.lower() or "Title" in chunks[0].content

    def test_chunks_toml_files(self, tmp_path: Path):
        """Should chunk .toml files as plain text."""
        (tmp_path / "manifest.toml").write_text(
            'version = 1\n\n[install]\npython3.pkg-path = "python3"\n'
        )

        chunks = chunk_document_directory(tmp_path, doc_type="skill", skill_name="test")

        assert len(chunks) >= 1
        assert "python3" in chunks[0].content

    def test_ignores_unsupported_files(self, tmp_path: Path):
        """Should skip files with unsupported extensions."""
        (tmp_path / "data.json").write_text('{"key": "value"}')
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        (tmp_path / "readme.md").write_text("# Readme\n\nActual content.")

        chunks = chunk_document_directory(tmp_path, doc_type="skill", skill_name="test")

        # Only the .md file should be chunked
        assert len(chunks) >= 1
        assert all("readme" in c.source_file.lower() or "Readme" in c.content for c in chunks)

    def test_empty_directory(self, tmp_path: Path):
        """Empty directory should return no chunks."""
        chunks = chunk_document_directory(tmp_path, doc_type="skill", skill_name="empty")
        assert chunks == []

    def test_content_hashes_unique(self, tmp_path: Path):
        """Each chunk should have a unique content hash."""
        (tmp_path / "a.md").write_text("# Doc A\n\nContent A about topic one.")
        (tmp_path / "b.md").write_text("# Doc B\n\nContent B about topic two.")

        chunks = chunk_document_directory(tmp_path, doc_type="flox_docs", skill_name="test")
        hashes = [c.content_hash for c in chunks]
        assert len(hashes) == len(set(hashes)), "Content hashes should be unique"
