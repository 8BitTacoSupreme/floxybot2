"""SQLAlchemy ORM models for FloxBot."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CanonChunk(Base):
    """RAG source chunks with vector embeddings."""

    __tablename__ = "canon_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_file: Mapped[str] = mapped_column(String(512), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    heading_hierarchy: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    chunk_index: Mapped[int] = mapped_column(nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="skill", index=True
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(512), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Content hash for idempotent upserts
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


class UserMemory(Base):
    """Per-user Tier 1 real-time memory."""

    __tablename__ = "user_memory"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_user_id: Mapped[str] = mapped_column(
        String(256), nullable=False, unique=True, index=True
    )
    skill_level: Mapped[str] = mapped_column(String(32), nullable=False, default="beginner")
    projects: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    past_issues: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    recent_skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    interaction_count: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Vote(Base):
    """Vote records for bot responses."""

    __tablename__ = "votes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    vote: Mapped[str] = mapped_column(
        Enum("up", "down", name="vote_type", create_constraint=True), nullable=False
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=True)
    response_text: Mapped[str] = mapped_column(Text, nullable=True)
    skills_used: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    org_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class Organization(Base):
    """Enterprise organization."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class OrgMember(Base):
    """Membership linking users to organizations."""

    __tablename__ = "org_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    canonical_user_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="member")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class Feedback(Base):
    """Structured user feedback."""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    user_id: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(
        Enum(
            "incorrect", "incomplete", "outdated", "confusing", "helpful", "other",
            name="feedback_category",
            create_constraint=True,
        ),
        nullable=False,
    )
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class Ticket(Base):
    """Support tickets created via Co-Pilot or escalation."""

    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    context_bundle: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class ChannelIdentity(Base):
    """Cross-channel user identity mapping."""

    __tablename__ = "channel_identities"
    __table_args__ = (
        Index("uq_channel_identity", "channel", "channel_user_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_user_id: Mapped[str] = mapped_column(
        String(256), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_user_id: Mapped[str] = mapped_column(String(256), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class Conversation(Base):
    """Conversation history keyed by conversation_id."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[str] = mapped_column(
        String(256), nullable=False, unique=True, index=True
    )
    user_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    messages: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
