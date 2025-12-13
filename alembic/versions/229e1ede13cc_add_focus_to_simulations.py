"""add focus to simulations

Revision ID: 229e1ede13cc
Revises: 20250101_0001
Create Date: 2025-12-13 14:57:29.391375

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '229e1ede13cc'
down_revision: Union[str, Sequence[str], None] = '20250101_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "simulations",
        sa.Column("focus", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("simulations", "focus")