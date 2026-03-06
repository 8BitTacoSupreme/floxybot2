"""Core types for the Central API."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Intent(str, Enum):
    CONVERSATIONAL = "conversational"
    CODE_GENERATION = "code_generation"
    DIAGNOSTIC = "diagnostic"
    TEACHING = "teaching"


class LLMBackend(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"


# Intent → backend routing map
INTENT_BACKEND_MAP: dict[Intent, LLMBackend] = {
    Intent.CONVERSATIONAL: LLMBackend.CLAUDE,
    Intent.CODE_GENERATION: LLMBackend.CODEX,
    Intent.DIAGNOSTIC: LLMBackend.CLAUDE,  # Claude orchestrates, delegates to Codex
    Intent.TEACHING: LLMBackend.CLAUDE,
}


class AuthResult(BaseModel):
    authenticated: bool = False
    floxhub_username: Optional[str] = None
    canonical_user_id: Optional[str] = None
    error: Optional[str] = None


class Entitlements(BaseModel):
    tier: str = "community"
    features: list[str] = Field(default_factory=list)
    rate_limit_rpm: int = 10
    skill_access: str = "basic"  # "basic", "full", "custom"
    codex_enabled: bool = False
    memory_enabled: bool = False
    copilot_modes: list[str] = Field(default_factory=lambda: ["ask", "chat"])
    org_id: str | None = None


class SkillPackage(BaseModel):
    name: str
    role: str = "primary"  # "primary" or "secondary"
    skill_md: str = ""
    prompts: list[str] = Field(default_factory=list)
    qa_pairs: list[dict] = Field(default_factory=list)
    token_budget: int = 8000  # primary=8k, secondary=4k


class BuiltContext(BaseModel):
    user_memory: dict = Field(default_factory=dict)
    rag_results: list[dict] = Field(default_factory=list)
    instance_knowledge: list[dict] = Field(default_factory=list)
    skills: list[SkillPackage] = Field(default_factory=list)
    project_context: dict = Field(default_factory=dict)
    conversation_history: list[dict] = Field(default_factory=list)
