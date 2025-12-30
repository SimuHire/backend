"""Add candidate access tokens for email verification.

Revision ID: 202504160001
Revises: 202504050001
Create Date: 2025-04-16 00:00:01.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202504160001"
down_revision: Union[str, Sequence[str], None] = "202504050001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidate_sessions",
        sa.Column("access_token", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column(
            "access_token_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_candidate_sessions_access_token"),
        "candidate_sessions",
        ["access_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_candidate_sessions_access_token"),
        table_name="candidate_sessions",
    )
    op.drop_column("candidate_sessions", "access_token_expires_at")
    op.drop_column("candidate_sessions", "access_token")
