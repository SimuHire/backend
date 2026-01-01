"""Add Auth0 identity fields to candidate sessions.

Revision ID: 202504250001
Revises: 202504160001
Create Date: 2025-04-25 00:00:01.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202504250001"
down_revision: Union[str, Sequence[str], None] = "202504160001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidate_sessions",
        sa.Column("candidate_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("candidate_auth0_sub", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidate_sessions", "claimed_at")
    op.drop_column("candidate_sessions", "candidate_auth0_sub")
    op.drop_column("candidate_sessions", "candidate_email")
