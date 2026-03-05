"""Normalized message schema — the canonical format for all channel adapters."""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Channel(str, Enum):
    SLACK = "slack"
    DISCORD = "discord"
    EMAIL = "email"
    CLI = "cli"
    COPILOT = "copilot"


class EntitlementTier(str, Enum):
    COMMUNITY = "community"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class UserIdentity(BaseModel):
    channel: Channel
    channel_user_id: str
    email: Optional[str] = None
    canonical_user_id: Optional[str] = None
    floxhub_username: Optional[str] = None
    entitlement_tier: EntitlementTier = EntitlementTier.COMMUNITY


class Attachment(BaseModel):
    filename: str
    content_type: str
    url: Optional[str] = None
    data: Optional[str] = None  # base64-encoded


class MessageContent(BaseModel):
    text: str
    attachments: list[Attachment] = Field(default_factory=list)
    code_blocks: list[str] = Field(default_factory=list)


class ProjectContext(BaseModel):
    has_flox_env: bool = False
    manifest: Optional[str] = None
    detected_skills: list[str] = Field(default_factory=list)


class MessageContext(BaseModel):
    project: Optional[ProjectContext] = None
    conversation_id: Optional[str] = None
    channel_metadata: dict = Field(default_factory=dict)


class SessionInfo(BaseModel):
    prior_messages: int = 0
    active_skills: list[str] = Field(default_factory=list)
    escalation_attempts: int = 0
    copilot_active: bool = False


class NormalizedMessage(BaseModel):
    """The canonical message format. Every adapter normalizes to this before
    hitting the Central API."""

    message_id: UUID = Field(default_factory=uuid4)
    user_identity: UserIdentity
    content: MessageContent
    context: MessageContext = Field(default_factory=MessageContext)
    session: SessionInfo = Field(default_factory=SessionInfo)
