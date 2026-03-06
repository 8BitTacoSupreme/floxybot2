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


class TestManifestInspection:
    """Tests for _inspect_manifest() — parsing manifest.toml packages to skills."""

    def test_detect_python_from_manifest(self):
        from src.skills.loader import _inspect_manifest
        manifest = '[install]\npython3.pkg-path = "python3"\nuv.pkg-path = "uv"\n'
        skills = _inspect_manifest(manifest)
        assert "python" in skills

    def test_detect_k8s_from_manifest(self):
        from src.skills.loader import _inspect_manifest
        manifest = '[install.kubectl]\npkg-path = "kubectl"\n[install.helm]\npkg-path = "helm"\n'
        skills = _inspect_manifest(manifest)
        assert "k8s" in skills

    def test_detect_multiple_skills(self):
        from src.skills.loader import _inspect_manifest
        manifest = '[install]\nkubectl.pkg-path = "kubectl"\nterraform.pkg-path = "terraform"\n'
        skills = _inspect_manifest(manifest)
        assert "k8s" in skills
        assert "terraform" in skills

    def test_no_mapped_packages(self):
        from src.skills.loader import _inspect_manifest
        manifest = '[install]\nhello.pkg-path = "hello"\n'
        skills = _inspect_manifest(manifest)
        assert skills == []

    def test_invalid_toml(self):
        from src.skills.loader import _inspect_manifest
        skills = _inspect_manifest("not valid toml {{{{")
        assert skills == []

    def test_pkg_path_mapping(self):
        from src.skills.loader import _inspect_manifest
        manifest = '[install.pg]\npkg-path = "postgresql_16"\n'
        skills = _inspect_manifest(manifest)
        assert "postgres" in skills

    @pytest.mark.asyncio
    async def test_manifest_inspection_highest_priority(self):
        """Manifest inspection scores higher than other signals."""
        manifest = '[install]\nkubectl.pkg-path = "kubectl"\n'
        context = BuiltContext(
            project_context={"manifest": manifest, "has_flox_env": True}
        )
        from src.skills.loader import detect_and_load_skills
        skills = await detect_and_load_skills(context)
        assert any(s.name == "k8s" for s in skills)


class TestMetadataLoading:
    """Tests for _load_metadata() and weight application."""

    def test_load_metadata_from_disk(self):
        from src.skills.loader import _load_metadata
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "skill-k8s"
            skill_dir.mkdir()
            (skill_dir / "metadata.json").write_text(
                '{"name": "k8s", "weight": 0.9, "triggers": ["kubectl"]}'
            )
            meta = _load_metadata("k8s", tmpdir)
            assert meta is not None
            assert meta["weight"] == 0.9

    def test_missing_metadata_returns_none(self):
        from src.skills.loader import _load_metadata
        with tempfile.TemporaryDirectory() as tmpdir:
            meta = _load_metadata("nonexistent", tmpdir)
            assert meta is None


class TestDiagnosticPrompts:
    """Tests for loading diagnostic prompt fragments."""

    def test_load_diagnostic_prompt(self):
        from src.skills.loader import _load_diagnostic_prompts
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "skill-k8s" / "prompts"
            skill_dir.mkdir(parents=True)
            (skill_dir / "diagnostic.md").write_text("# K8s Diagnostics\nCheck pod status.")
            prompts = _load_diagnostic_prompts("k8s", tmpdir)
            assert len(prompts) == 1
            assert "Check pod status" in prompts[0]

    def test_no_prompts_dir(self):
        from src.skills.loader import _load_diagnostic_prompts
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts = _load_diagnostic_prompts("nonexistent", tmpdir)
            assert prompts == []

    @pytest.mark.asyncio
    async def test_diagnostic_intent_loads_prompts(self):
        """When intent=diagnostic, skill packages include prompts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "skill-k8s"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# K8s")
            prompts_dir = skill_dir / "prompts"
            prompts_dir.mkdir()
            (prompts_dir / "diagnostic.md").write_text("Check pods first.")

            context = BuiltContext()
            message = {"content": {"text": "my k8s pod is crashing"}}

            with patch("src.config.settings.SKILLS_PATH", tmpdir):
                from src.skills.loader import detect_and_load_skills
                skills = await detect_and_load_skills(context, message=message, intent="diagnostic")

            k8s_skill = [s for s in skills if s.name == "k8s"]
            assert len(k8s_skill) == 1
            assert len(k8s_skill[0].prompts) == 1
            assert "Check pods first" in k8s_skill[0].prompts[0]


class TestSkillPackageStructure:
    """Validate all skill packages in the repo have required files."""

    def test_all_skills_have_skill_md(self):
        skills_path = Path("/Users/jhogan/floxybot2/skills")
        for skill_dir in skills_path.iterdir():
            if skill_dir.is_dir() and not skill_dir.name.startswith("."):
                assert (skill_dir / "SKILL.md").is_file(), f"{skill_dir.name} missing SKILL.md"

    def test_all_skills_have_metadata(self):
        skills_path = Path("/Users/jhogan/floxybot2/skills")
        for skill_dir in skills_path.iterdir():
            if skill_dir.is_dir() and not skill_dir.name.startswith("."):
                meta_path = skill_dir / "metadata.json"
                assert meta_path.is_file(), f"{skill_dir.name} missing metadata.json"
                import json
                meta = json.loads(meta_path.read_text())
                assert "name" in meta
                assert "triggers" in meta
                assert isinstance(meta["triggers"], list)

    def test_all_skills_have_diagnostic_prompts(self):
        skills_path = Path("/Users/jhogan/floxybot2/skills")
        for skill_dir in skills_path.iterdir():
            if skill_dir.is_dir() and not skill_dir.name.startswith("."):
                assert (skill_dir / "prompts" / "diagnostic.md").is_file(), \
                    f"{skill_dir.name} missing prompts/diagnostic.md"
