"""Tests for user memory post-interaction updates."""

from __future__ import annotations

import pytest

from src.memory.user import build_memory_update, infer_skill_level, MAX_RECENT_SKILLS


class TestBuildMemoryUpdate:
    def _response(self, **overrides):
        base = {"status": "ok", "text": "test response", "skills_used": []}
        base.update(overrides)
        return base

    def _message(self, text="hello", code_blocks=None, detected_skills=None, manifest=None):
        msg = {
            "content": {"text": text, "code_blocks": code_blocks or []},
            "context": {
                "project": {
                    "has_flox_env": bool(manifest),
                    "manifest": manifest,
                    "detected_skills": detected_skills or [],
                }
            },
        }
        return msg

    def test_tracks_skills_used(self):
        resp = self._response(skills_used=[{"name": "k8s", "role": "primary"}])
        updates = build_memory_update(resp, self._message(), "conversational")
        assert updates["recent_skills"] == ["k8s"]

    def test_tracks_multiple_skills(self):
        resp = self._response(
            skills_used=[
                {"name": "terraform", "role": "primary"},
                {"name": "aws", "role": "secondary"},
            ]
        )
        updates = build_memory_update(resp, self._message(), "code_generation")
        assert updates["recent_skills"] == ["terraform", "aws"]

    def test_increments_interaction_count(self):
        resp = self._response()
        updates = build_memory_update(resp, self._message(), "conversational")
        assert updates["interaction_count"] == 1

    def test_extracts_project_skills(self):
        msg = self._message(detected_skills=["python", "postgres"])
        updates = build_memory_update(self._response(), msg, "conversational")
        assert "python" in updates["projects"]
        assert "postgres" in updates["projects"]

    def test_code_blocks_set_intermediate(self):
        msg = self._message(code_blocks=["import os"])
        updates = build_memory_update(self._response(), msg, "code_generation")
        assert updates["skill_level"] == "intermediate"

    def test_manifest_sets_intermediate(self):
        msg = self._message(manifest="[install]\npython3 = {}")
        updates = build_memory_update(self._response(), msg, "conversational")
        assert updates["skill_level"] == "intermediate"

    def test_no_code_no_skill_level_override(self):
        msg = self._message(text="hello")
        updates = build_memory_update(self._response(), msg, "conversational")
        assert "skill_level" not in updates

    def test_string_skills_used(self):
        resp = self._response(skills_used=["k8s", "docker"])
        updates = build_memory_update(resp, self._message(), "conversational")
        assert updates["recent_skills"] == ["k8s", "docker"]


class TestInferSkillLevel:
    def test_beginner(self):
        assert infer_skill_level(5) == "beginner"

    def test_intermediate_by_count(self):
        assert infer_skill_level(15) == "intermediate"

    def test_intermediate_by_code(self):
        assert infer_skill_level(3, has_code=True) == "intermediate"

    def test_advanced(self):
        assert infer_skill_level(50, has_code=True) == "advanced"


class TestRecentSkillsLimit:
    def test_max_recent_skills_constant(self):
        assert MAX_RECENT_SKILLS == 10
