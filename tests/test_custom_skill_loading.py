"""Tests for custom skill loading (enterprise)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.models.types import BuiltContext, Entitlements
from src.skills.loader import _get_skill_search_paths, _resolve_skill_dir, detect_and_load_skills


class TestGetSkillSearchPaths:
    def test_basic_returns_single_path(self):
        ent = Entitlements(skill_access="basic")
        paths = _get_skill_search_paths(ent)
        assert len(paths) == 1

    def test_full_returns_single_path(self):
        ent = Entitlements(skill_access="full")
        paths = _get_skill_search_paths(ent)
        assert len(paths) == 1

    def test_custom_returns_two_paths(self):
        ent = Entitlements(skill_access="custom")
        paths = _get_skill_search_paths(ent)
        assert len(paths) == 2

    def test_none_entitlements_returns_single(self):
        paths = _get_skill_search_paths(None)
        assert len(paths) == 1


class TestCustomSkillResolution:
    def test_resolve_from_custom_path(self):
        with tempfile.TemporaryDirectory() as custom_dir:
            (Path(custom_dir) / "my-custom-skill").mkdir()
            result = _resolve_skill_dir("my-custom-skill", ["/nonexistent", custom_dir])
            assert result is not None
            assert result.name == "my-custom-skill"

    def test_primary_path_takes_precedence(self):
        with tempfile.TemporaryDirectory() as dir1, tempfile.TemporaryDirectory() as dir2:
            (Path(dir1) / "skill-k8s").mkdir()
            (Path(dir2) / "skill-k8s").mkdir()
            result = _resolve_skill_dir("k8s", [dir1, dir2])
            assert str(dir1) in str(result)


class TestCustomSkillLoading:
    @pytest.mark.asyncio
    async def test_custom_skill_found_and_loaded(self):
        """Enterprise custom entitlement can load from custom skills dir."""
        with tempfile.TemporaryDirectory() as custom_dir:
            skill_dir = Path(custom_dir) / "my-org-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# My Org Skill\nCustom content.")

            ent = Entitlements(skill_access="custom")

            with patch("src.config.settings.SKILLS_PATH", "/nonexistent"), \
                 patch("src.config.settings.CUSTOM_SKILLS_PATH", custom_dir):
                context = BuiltContext(
                    project_context={"detected_skills": ["my-org-skill"]}
                )
                skills = await detect_and_load_skills(context, entitlements=ent)

            assert len(skills) >= 1
            assert any(s.name == "my-org-skill" for s in skills)
            loaded = [s for s in skills if s.name == "my-org-skill"][0]
            assert "Custom content" in loaded.skill_md

    @pytest.mark.asyncio
    async def test_backward_compat_none_entitlements(self):
        """None entitlements (backward compat) only searches SKILLS_PATH."""
        context = BuiltContext(project_context={"detected_skills": ["terraform"]})
        skills = await detect_and_load_skills(context, entitlements=None)
        # Should not crash; terraform may or may not be found depending on disk
        assert isinstance(skills, list)
