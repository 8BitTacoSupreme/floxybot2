"""API response schemas."""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ResponseStatus(str, Enum):
    OK = "ok"
    ESCALATED = "escalated"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


class SkillUsed(BaseModel):
    name: str
    role: str  # "primary" or "secondary"
    tokens_used: int


class BotResponse(BaseModel):
    response_id: UUID = Field(default_factory=uuid4)
    message_id: UUID
    status: ResponseStatus
    text: str
    code_blocks: list[str] = Field(default_factory=list)
    skills_used: list[SkillUsed] = Field(default_factory=list)
    confidence: float = 0.0
    llm_backend: Optional[str] = None  # "claude" or "codex"
    escalation_reason: Optional[str] = None
    suggested_votes: bool = True
