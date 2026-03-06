"""Phase 2 — tickets table.

Revision ID: 002
Revises: 001
Create Date: 2026-03-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.String(256), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("context_bundle", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("priority", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tickets_user_id", "tickets", ["user_id"])


def downgrade() -> None:
    op.drop_table("tickets")
