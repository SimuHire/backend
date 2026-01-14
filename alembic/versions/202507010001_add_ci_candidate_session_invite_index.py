"""Add case-insensitive unique invite index for candidate sessions.

Revision ID: 202507010001
Revises: 202506150002
Create Date: 2025-07-01 00:00:01.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202507010001"
down_revision: Union[str, Sequence[str], None] = "202506150002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CI_UNIQUE_INDEX = "uq_candidate_sessions_simulation_invite_email_ci"


def upgrade() -> None:
    op.execute(
        """
        UPDATE candidate_sessions
        SET invite_email = lower(trim(invite_email))
        WHERE invite_email IS NOT NULL
        """
    )
    op.create_index(
        _CI_UNIQUE_INDEX,
        "candidate_sessions",
        ["simulation_id", sa.text("lower(invite_email)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(_CI_UNIQUE_INDEX, table_name="candidate_sessions")
