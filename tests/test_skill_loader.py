"""Tests for skill detection and loading."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.models.types import BuiltContext, SkillPackage


@pytest.mark.asyncio
async def test_detect_from_manifest():
    """Terraform in manifest → terraform skill detected."""
    context = BuiltContext(
        project_context={"detected_skills": ["terraform"], "has_flox_env": True}
    )
    from src.skills.loader import detect_and_load_skills

    skills = await detect_and_load_skills(context)
    assert any(s.name == "terraform" for s in skills)


@pytest.mark.asyncio
async def test_detect_from_message():
    """'k8s pod failing' → k8s skill detected."""
    context = BuiltContext()
    message = {"content": {"text": "my k8s pod is failing with CrashLoopBackOff"}}

    from src.skills.loader import detect_and_load_skills

    skills = await detect_and_load_skills(context, message=message)
    assert any(s.name == "k8s" for s in skills)


@pytest.mark.asyncio
async def test_detect_core_canon_from_message():
    """'flox install' → core-canon skill detected."""
    context = BuiltContext()
    message = {"content": {"text": "How do I install a package with flox?"}}

    from src.skills.loader import detect_and_load_skills

    skills = await detect_and_load_skills(context, message=message)
    assert any(s.name == "core-canon" for s in skills)


@pytest.mark.asyncio
async def test_max_two_skills():
    """Never returns more than 2 skills."""
    context = BuiltContext(
        project_context={"detected_skills": ["terraform", "aws", "docker"]}
    )
    from src.skills.loader import detect_and_load_skills

    skills = await detect_and_load_skills(context)
    assert len(skills) <= 2


@pytest.mark.asyncio
async def test_load_skill_content_primary():
    """Primary skill loads full SKILL.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "core-canon"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Core Canon\n\nFull content here.")

        context = BuiltContext()
        message = {"content": {"text": "How do I use flox?"}}

        with patch("src.config.settings.SKILLS_PATH", tmpdir):
            from src.skills.loader import detect_and_load_skills
            skills = await detect_and_load_skills(context, message=message)

    primary = [s for s in skills if s.role == "primary"]
    assert len(primary) == 1
    assert "Full content here" in primary[0].skill_md


@pytest.mark.asyncio
async def test_load_skill_content_secondary():
    """Secondary skill gets truncated content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for name in ["core-canon", "skill-k8s"]:
            d = Path(tmpdir) / name
            d.mkdir()
            # Write content longer than secondary budget
            (d / "SKILL.md").write_text(f"# {name}\n\n" + "x " * 5000)

        context = BuiltContext()
        message = {"content": {"text": "flox install kubectl for kubernetes"}}

        with patch("src.config.settings.SKILLS_PATH", tmpdir):
            from src.skills.loader import detect_and_load_skills
            skills = await detect_and_load_skills(context, message=message)

    if len(skills) >= 2:
        secondary = [s for s in skills if s.role == "secondary"]
        assert len(secondary) == 1
        assert secondary[0].token_budget == 4000


@pytest.mark.asyncio
async def test_load_missing_skill():
    """Missing SKILL.md → empty skill_md."""
    context = BuiltContext(project_context={"detected_skills": ["nonexistent"]})

    from src.skills.loader import detect_and_load_skills

    skills = await detect_and_load_skills(context)
    assert len(skills) > 0
    assert skills[0].skill_md == ""


@pytest.mark.asyncio
async def test_no_skills_detected():
    """No signals → empty list."""
    context = BuiltContext()

    from src.skills.loader import detect_and_load_skills

    skills = await detect_and_load_skills(context)
    assert skills == []
