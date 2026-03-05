"""Initial schema — all Phase 1 tables + pgvector extension.

Revision ID: 001
Revises: None
Create Date: 2026-03-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- canon_chunks ---
    op.create_table(
        "canon_chunks",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("source_file", sa.String(512), nullable=False),
        sa.Column("skill_name", sa.String(128), nullable=False),
        sa.Column("heading_hierarchy", sa.String(512), nullable=False, server_default=""),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_canon_chunks_skill_name", "canon_chunks", ["skill_name"])

    # IVFFlat index on embeddings for cosine similarity search
    # Use lists=100 for small datasets; scale with sqrt(n_rows) for larger
    op.execute(
        "CREATE INDEX ix_canon_chunks_embedding ON canon_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # --- user_memory ---
    op.create_table(
        "user_memory",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("canonical_user_id", sa.String(256), nullable=False, unique=True),
        sa.Column("skill_level", sa.String(32), nullable=False, server_default="beginner"),
        sa.Column("projects", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("past_issues", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("preferences", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_memory_canonical_user_id", "user_memory", ["canonical_user_id"])

    # --- votes ---
    op.execute("DO $$ BEGIN CREATE TYPE vote_type AS ENUM ('up', 'down'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    op.create_table(
        "votes",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.String(256), nullable=False),
        sa.Column("user_id", sa.String(256), nullable=False),
        sa.Column("vote", PG_ENUM("up", "down", name="vote_type", create_type=False), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("skills_used", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_votes_message_id", "votes", ["message_id"])
    op.create_index("ix_votes_conversation_id", "votes", ["conversation_id"])
    op.create_index("ix_votes_user_id", "votes", ["user_id"])

    # --- feedback ---
    op.execute("DO $$ BEGIN CREATE TYPE feedback_category AS ENUM ('incorrect', 'incomplete', 'outdated', 'confusing', 'helpful', 'other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    op.create_table(
        "feedback",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.String(256), nullable=False),
        sa.Column("user_id", sa.String(256), nullable=False),
        sa.Column("category", PG_ENUM("incorrect", "incomplete", "outdated", "confusing", "helpful", "other", name="feedback_category", create_type=False), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_feedback_message_id", "feedback", ["message_id"])

    # --- conversations ---
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("conversation_id", sa.String(256), nullable=False, unique=True),
        sa.Column("user_id", sa.String(256), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_conversations_conversation_id", "conversations", ["conversation_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])


def downgrade() -> None:
    op.drop_table("conversations")
    op.drop_table("feedback")
    op.drop_table("votes")
    op.drop_table("user_memory")
    op.drop_table("canon_chunks")

    op.execute("DROP TYPE IF EXISTS feedback_category")
    op.execute("DROP TYPE IF EXISTS vote_type")
    op.execute("DROP EXTENSION IF EXISTS vector")
