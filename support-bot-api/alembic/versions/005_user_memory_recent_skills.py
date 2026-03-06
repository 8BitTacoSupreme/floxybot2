"""Add recent_skills and interaction_count to user_memory.

Revision ID: 005
Revises: 004
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_memory", sa.Column("recent_skills", JSONB, nullable=False, server_default="[]"))
    op.add_column("user_memory", sa.Column("interaction_count", sa.Integer, nullable=False, server_default="0"))


def downgrade():
    op.drop_column("user_memory", "interaction_count")
    op.drop_column("user_memory", "recent_skills")
