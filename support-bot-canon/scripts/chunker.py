"""Section-aware markdown chunking for canon ingest."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Chunk:
    content: str
    source_file: str
    skill_name: str
    heading_hierarchy: str = ""
    chunk_index: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(
            f"{self.source_file}:{self.skill_name}:{self.chunk_index}:{self.content}".encode()
        ).hexdigest()


def chunk_markdown(
    filepath: str | Path,
    chunk_size: int = 512,
    overlap: int = 64,
    skill_name: str = "",
) -> list[Chunk]:
    """Split a markdown file into chunks, respecting headings and code blocks.

    - Never splits inside code fences
    - Splits on ## headings first, then by token count
    - Each chunk retains its heading hierarchy as a prefix
    """
    filepath = Path(filepath)
    text = filepath.read_text()
    source = str(filepath)

    if not skill_name:
        skill_name = filepath.parent.name

    sections = _split_by_headings(text)
    chunks: list[Chunk] = []
    idx = 0

    for heading, body in sections:
        sub_chunks = _split_section(body, chunk_size, overlap)
        for sub in sub_chunks:
            content = f"{heading}\n\n{sub}".strip() if heading else sub.strip()
            if content:
                chunks.append(Chunk(
                    content=content,
                    source_file=source,
                    skill_name=skill_name,
                    heading_hierarchy=heading,
                    chunk_index=idx,
                ))
                idx += 1

    return chunks


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """Split text into (heading, body) pairs on ## headings."""
    # Match lines starting with ## (level 2+)
    pattern = re.compile(r"^(#{2,}\s+.+)$", re.MULTILINE)
    parts = pattern.split(text)

    sections: list[tuple[str, str]] = []
    current_heading = ""

    i = 0
    while i < len(parts):
        part = parts[i]
        if pattern.match(part.strip()):
            current_heading = part.strip()
            i += 1
        else:
            body = part
            sections.append((current_heading, body))
            i += 1

    return sections


def _split_section(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split a section into chunks by approximate word count, preserving code blocks."""
    if not text.strip():
        return []

    # Extract code blocks to protect them
    code_block_pattern = re.compile(r"(```[\s\S]*?```)", re.MULTILINE)
    blocks = code_block_pattern.split(text)

    # Build segments that are either text or code blocks
    segments: list[str] = []
    for block in blocks:
        if block.startswith("```"):
            segments.append(block)
        else:
            # Split text by paragraphs
            paragraphs = re.split(r"\n\n+", block)
            segments.extend([p for p in paragraphs if p.strip()])

    # Combine segments into chunks respecting size
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for segment in segments:
        seg_words = len(segment.split())
        if current_words + seg_words > chunk_size and current:
            chunks.append("\n\n".join(current))
            # Overlap: keep last segment if it fits
            if overlap > 0 and current:
                last = current[-1]
                if len(last.split()) <= overlap:
                    current = [last]
                    current_words = len(last.split())
                else:
                    current = []
                    current_words = 0
            else:
                current = []
                current_words = 0
        current.append(segment)
        current_words += seg_words

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def chunk_skill_package(skill_dir: str | Path) -> list[Chunk]:
    """Index all documents in a skill package directory.

    Processes:
    - SKILL.md (primary)
    - metadata.json (as a chunk)
    - Any .md files in prompts/ or qa/
    """
    skill_dir = Path(skill_dir)
    skill_name = skill_dir.name
    all_chunks: list[Chunk] = []

    # SKILL.md
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        all_chunks.extend(chunk_markdown(skill_md, skill_name=skill_name))

    # metadata.json
    meta_file = skill_dir / "metadata.json"
    if meta_file.is_file():
        try:
            meta = json.loads(meta_file.read_text())
            content = f"# {skill_name} metadata\n\n{json.dumps(meta, indent=2)}"
            all_chunks.append(Chunk(
                content=content,
                source_file=str(meta_file),
                skill_name=skill_name,
                heading_hierarchy=f"# {skill_name} metadata",
                chunk_index=len(all_chunks),
                metadata=meta,
            ))
        except (json.JSONDecodeError, OSError):
            pass

    # Additional .md files in subdirectories
    for subdir in ["prompts", "qa", "examples"]:
        sub_path = skill_dir / subdir
        if sub_path.is_dir():
            for md_file in sorted(sub_path.glob("*.md")):
                chunks = chunk_markdown(md_file, skill_name=skill_name)
                for c in chunks:
                    c.chunk_index = len(all_chunks)
                    all_chunks.append(c)

    return all_chunks
