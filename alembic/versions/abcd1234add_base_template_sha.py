"""Add base_template_sha to workspaces

Revision ID: abcd1234addb
Revises: 9e3c4e0d4a10
Create Date: 2025-02-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "abcd1234addb"
down_revision: Union[str, Sequence[str], None] = "9e3c4e0d4a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("base_template_sha", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "base_template_sha")
