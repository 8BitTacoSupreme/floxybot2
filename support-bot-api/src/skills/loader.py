"""Skill detection and loading — max 2 per turn."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..models.types import BuiltContext, Entitlements, SkillPackage

logger = logging.getLogger(__name__)

# Detection signal priority (ranked by confidence):
# 1. Manifest inspection (ground truth)
# 2. Project context detected_skills
# 3. Message content analysis
# 4. User memory

SKILL_TRIGGERS: dict[str, list[str]] = {
    "k8s": ["kubernetes", "kubectl", "k8s", "pod", "deployment", "helm", "kustomize"],
    "terraform": ["terraform", "tf", "hcl", "provider", "tfstate"],
    "aws": ["aws", "ec2", "s3", "lambda", "cloudformation", "iam"],
    "gcp": ["gcp", "gcloud", "cloud run", "bigquery", "gke"],
    "docker": ["docker", "dockerfile", "container", "compose", "podman"],
    "postgres": ["postgres", "postgresql", "psql", "pg_dump"],
    "rust": ["rust", "cargo", "rustc", "crate"],
    "python": ["python", "pip", "venv", "pyproject", "poetry"],
}

# Core-canon is always implicitly available
CORE_SKILL_TRIGGERS = ["flox", "manifest", "environment", "package", "install", "activate"]

# Map manifest [install] package names → skill names
PACKAGE_SKILL_MAP: dict[str, str] = {
    "kubectl": "k8s", "helm": "k8s", "kustomize": "k8s", "kind": "k8s",
    "k9s": "k8s", "minikube": "k8s",
    "terraform": "terraform", "opentofu": "terraform",
    "awscli2": "aws", "aws-vault": "aws", "aws-sam-cli": "aws",
    "google-cloud-sdk": "gcp",
    "docker": "docker", "podman": "docker", "docker-compose": "docker",
    "postgresql": "postgres", "postgresql_16": "postgres", "pgcli": "postgres",
    "postgresql_15": "postgres",
    "rustc": "rust", "cargo": "rust",
    "python3": "python", "python311": "python", "python312": "python",
    "uv": "python", "poetry": "python",
}


def _get_skill_search_paths(entitlements: Entitlements | None = None) -> list[str]:
    """Return skill directory search paths based on entitlement level."""
    from src.config import settings

    paths = [settings.SKILLS_PATH]
    if entitlements is not None and entitlements.skill_access == "custom":
        paths.append(settings.CUSTOM_SKILLS_PATH)
    return paths


async def detect_and_load_skills(
    context: BuiltContext,
    message: dict[str, Any] | None = None,
    intent: str = "conversational",
    entitlements: Entitlements | None = None,
) -> list[SkillPackage]:
    """Detect relevant skills and load up to 2 packages.

    Detection signals (ordered by confidence):
    0. Manifest inspection — packages in user's manifest.toml
    1. Project context detected_skills
    2. Message text keyword scanning
    3. User memory (recent skill usage)

    Primary skill gets full load (~8k tokens).
    Secondary skill gets summary (~4k tokens).
    """
    from src.config import settings

    scores: dict[str, float] = {}

    # 0. Manifest inspection (highest confidence — ground truth)
    project = context.project_context
    if isinstance(project, dict) and project.get("manifest"):
        manifest_skills = _inspect_manifest(project["manifest"])
        for skill in manifest_skills:
            scores[skill] = scores.get(skill, 0) + 3.5

    # 1. Project context detected skills
    if isinstance(project, dict):
        for skill in project.get("detected_skills", []):
            scores[skill] = scores.get(skill, 0) + 3.0

    # 2. Message text scanning
    if message is not None:
        text = message.get("content", {}).get("text", "").lower()
        if text:
            # Check core-canon triggers first
            for trigger in CORE_SKILL_TRIGGERS:
                if trigger in text:
                    scores["core-canon"] = scores.get("core-canon", 0) + 2.0
                    break

            # Check skill-specific triggers
            for skill_name, triggers in SKILL_TRIGGERS.items():
                for trigger in triggers:
                    if trigger in text:
                        scores[skill_name] = scores.get(skill_name, 0) + 1.5
                        break

    # 3. User memory (lower confidence)
    if context.user_memory:
        recent_skills = context.user_memory.get("recent_skills", [])
        for skill in recent_skills:
            scores[skill] = scores.get(skill, 0) + 0.5

    if not scores:
        return []

    # Determine search paths based on entitlements
    search_paths = _get_skill_search_paths(entitlements)

    # Apply metadata weights
    for skill_name in list(scores.keys()):
        metadata = _load_metadata(skill_name, search_paths)
        if metadata and "weight" in metadata:
            scores[skill_name] *= metadata["weight"]

    # Sort by score, take top 2
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_skills = ranked[: settings.MAX_SKILLS_PER_TURN]

    # Load skill packages
    skills: list[SkillPackage] = []
    for i, (skill_name, score) in enumerate(top_skills):
        role = "primary" if i == 0 else "secondary"
        budget = (
            settings.PRIMARY_SKILL_TOKEN_BUDGET
            if role == "primary"
            else settings.SECONDARY_SKILL_TOKEN_BUDGET
        )

        skill_md = _load_skill_md(skill_name, budget, search_paths)
        prompts = _load_diagnostic_prompts(skill_name, search_paths) if intent == "diagnostic" else []

        skills.append(
            SkillPackage(
                name=skill_name,
                role=role,
                skill_md=skill_md,
                prompts=prompts,
                token_budget=budget,
            )
        )

    return skills


def _inspect_manifest(manifest_text: str) -> list[str]:
    """Parse manifest.toml and map installed packages to skills."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    try:
        parsed = tomllib.loads(manifest_text)
    except Exception:
        logger.debug("Failed to parse manifest for skill detection")
        return []

    install = parsed.get("install", {})
    detected: set[str] = set()
    for pkg_name in install:
        # Check direct name
        if pkg_name in PACKAGE_SKILL_MAP:
            detected.add(PACKAGE_SKILL_MAP[pkg_name])
        # Check pkg-path if present
        pkg_path = install[pkg_name].get("pkg-path", "") if isinstance(install[pkg_name], dict) else ""
        if pkg_path in PACKAGE_SKILL_MAP:
            detected.add(PACKAGE_SKILL_MAP[pkg_path])

    return list(detected)


def _load_metadata(skill_name: str, search_paths: str | list[str]) -> dict | None:
    """Load metadata.json for a skill package."""
    skill_dir = _resolve_skill_dir(skill_name, search_paths)
    if not skill_dir:
        return None

    meta_path = skill_dir / "metadata.json"
    if not meta_path.is_file():
        return None

    try:
        return json.loads(meta_path.read_text())
    except Exception:
        logger.debug("Failed to parse metadata.json for %s", skill_name)
        return None


def _load_diagnostic_prompts(skill_name: str, search_paths: str | list[str]) -> list[str]:
    """Load diagnostic prompt fragments for a skill."""
    skill_dir = _resolve_skill_dir(skill_name, search_paths)
    if not skill_dir:
        return []

    diag_path = skill_dir / "prompts" / "diagnostic.md"
    if not diag_path.is_file():
        return []

    try:
        return [diag_path.read_text()]
    except Exception:
        return []


def _resolve_skill_dir(skill_name: str, search_paths: str | list[str]) -> Path | None:
    """Resolve skill directory, trying paths in order with bare name and skill- prefix."""
    if isinstance(search_paths, str):
        search_paths = [search_paths]

    for skills_path in search_paths:
        skill_dir = Path(skills_path) / skill_name
        if skill_dir.is_dir():
            return skill_dir

        skill_dir = Path(skills_path) / f"skill-{skill_name}"
        if skill_dir.is_dir():
            return skill_dir

    return None


def _load_skill_md(skill_name: str, budget: int, search_paths: str | list[str]) -> str:
    """Load SKILL.md content from disk, truncated to budget."""
    skill_dir = _resolve_skill_dir(skill_name, search_paths)
    if not skill_dir:
        logger.debug("Skill directory not found for %s", skill_name)
        return ""

    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.is_file():
        logger.debug("SKILL.md not found for %s", skill_name)
        return ""

    content = skill_md_path.read_text()

    # Rough truncation to token budget (1 token ≈ 4 chars)
    max_chars = budget * 4
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n[... truncated for token budget ...]"

    return content
