"""Add execution profiles

Revision ID: fa61fe2e7edd
Revises: b5e134bdb971
Create Date: 2025-12-17 12:19:41.461662

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'fa61fe2e7edd'
down_revision: Union[str, Sequence[str], None] = 'b5e134bdb971'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "candidate_session_id",
            sa.Integer(),
            sa.ForeignKey("candidate_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_execution_profiles_candidate_session_id",
        "execution_profiles",
        ["candidate_session_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_execution_profiles_candidate_session_id", table_name="execution_profiles")
    op.drop_table("execution_profiles")