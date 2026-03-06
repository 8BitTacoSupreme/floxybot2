"""Add channel_identities table for cross-channel user mapping.

Revision ID: 004
Revises: 003
Create Date: 2026-03-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channel_identities",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("canonical_user_id", sa.String(256), nullable=False),
        sa.Column("channel", sa.String(64), nullable=False),
        sa.Column("channel_user_id", sa.String(256), nullable=False),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_channel_identities_canonical_user_id", "channel_identities", ["canonical_user_id"])
    op.create_index("uq_channel_identity", "channel_identities", ["channel", "channel_user_id"], unique=True)


def downgrade() -> None:
    op.drop_table("channel_identities")
