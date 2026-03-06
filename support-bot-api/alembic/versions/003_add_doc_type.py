"""Add doc_type column to canon_chunks.

Revision ID: 003
Revises: 002
Create Date: 2026-03-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "canon_chunks",
        sa.Column("doc_type", sa.String(64), nullable=False, server_default="skill"),
    )
    op.create_index("ix_canon_chunks_doc_type", "canon_chunks", ["doc_type"])


def downgrade() -> None:
    op.drop_index("ix_canon_chunks_doc_type", table_name="canon_chunks")
    op.drop_column("canon_chunks", "doc_type")
