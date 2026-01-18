"""Add indexes for submissions and tasks lookups

Revision ID: 202507200001
Revises: 202507150001
Create Date: 2025-07-20 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202507200001"
down_revision: Union[str, Sequence[str], None] = "202507150001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_submissions_candidate_session_id",
        "submissions",
        ["candidate_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_tasks_simulation_day_index",
        "tasks",
        ["simulation_id", "day_index"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_simulation_day_index", table_name="tasks")
    op.drop_index("ix_submissions_candidate_session_id", table_name="submissions")
