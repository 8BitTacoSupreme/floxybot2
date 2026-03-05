"""Skill detection and loading — max 2 per turn."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..models.types import BuiltContext, SkillPackage

logger = logging.getLogger(__name__)

# Detection signal priority (ranked by confidence):
# 1. Manifest inspection
# 2. Message content analysis
# 3. User memory
# 4. Conversation history

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


async def detect_and_load_skills(
    context: BuiltContext,
    message: dict[str, Any] | None = None,
) -> list[SkillPackage]:
    """Detect relevant skills and load up to 2 packages.

    Detection signals:
    1. Project context (detected_skills from manifest parsing)
    2. Message text keyword scanning
    3. User memory (recent skill usage)

    Primary skill gets full load (~8k tokens).
    Secondary skill gets summary (~4k tokens).
    """
    from src.config import settings

    scores: dict[str, float] = {}

    # 1. Project context detected skills (highest confidence)
    project = context.project_context
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

        skill_md = _load_skill_md(skill_name, budget, settings.SKILLS_PATH)

        skills.append(
            SkillPackage(
                name=skill_name,
                role=role,
                skill_md=skill_md,
                token_budget=budget,
            )
        )

    return skills


def _load_skill_md(skill_name: str, budget: int, skills_path: str) -> str:
    """Load SKILL.md content from disk, truncated to budget."""
    skill_dir = Path(skills_path) / skill_name
    skill_md_path = skill_dir / "SKILL.md"

    if not skill_md_path.is_file():
        # Try with skill- prefix
        skill_dir = Path(skills_path) / f"skill-{skill_name}"
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
