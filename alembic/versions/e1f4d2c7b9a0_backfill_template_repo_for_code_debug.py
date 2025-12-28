"""Backfill template_repo for code/debug tasks

Revision ID: e1f4d2c7b9a0
Revises: abcd1234addb
Create Date: 2025-03-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f4d2c7b9a0"
down_revision: Union[str, Sequence[str], None] = "abcd1234addb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Populate template_repo for existing code/debug tasks if missing."""
    template_mapping = {
        2: "simuhire-templates/node-day2-api",
        3: "simuhire-templates/node-day3-debug",
    }
    for day_index, repo in template_mapping.items():
        op.execute(
            sa.text(
                """
                UPDATE tasks
                SET template_repo = :repo
                WHERE (template_repo IS NULL OR template_repo = '')
                  AND type IN ('code', 'debug')
                  AND day_index = :day_index
                """
            ).bindparams(repo=repo, day_index=day_index)
        )


def downgrade() -> None:
    """Clear backfilled template_repo values to restore previous state."""
    template_mapping = {
        2: "simuhire-templates/node-day2-api",
        3: "simuhire-templates/node-day3-debug",
    }
    for day_index, repo in template_mapping.items():
        op.execute(
            sa.text(
                """
                UPDATE tasks
                SET template_repo = NULL
                WHERE template_repo = :repo
                  AND type IN ('code', 'debug')
                  AND day_index = :day_index
                """
            ).bindparams(repo=repo, day_index=day_index)
        )
