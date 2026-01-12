"""Add candidate_auth0_email to candidate sessions.

Revision ID: 202506150002
Revises: 202506150001
Create Date: 2025-06-15 00:00:02.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202506150002"
down_revision: Union[str, Sequence[str], None] = "202506150001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("candidate_sessions")}
    if "candidate_auth0_email" not in columns:
        op.add_column(
            "candidate_sessions",
            sa.Column("candidate_auth0_email", sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("candidate_sessions", "candidate_auth0_email")
