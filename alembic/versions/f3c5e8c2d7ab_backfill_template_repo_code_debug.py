"""Backfill template_repo for code/debug tasks to GitHub templates

Revision ID: f3c5e8c2d7ab
Revises: e1f4d2c7b9a0
Create Date: 2025-03-06 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3c5e8c2d7ab"
down_revision: Union[str, Sequence[str], None] = "e1f4d2c7b9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEMPLATE_REPO = "simuhire-dev/simuhire-template-python"


def upgrade() -> None:
    """Set a default template repo for code/debug tasks that are empty."""
    op.execute(
        sa.text(
            """
            UPDATE tasks
            SET template_repo = :repo
            WHERE type IN ('code', 'debug')
              AND (template_repo IS NULL OR btrim(template_repo) = '')
            """
        ).bindparams(repo=TEMPLATE_REPO)
    )


def downgrade() -> None:
    """Revert backfilled rows."""
    op.execute(
        sa.text(
            """
            UPDATE tasks
            SET template_repo = NULL
            WHERE type IN ('code', 'debug')
              AND template_repo = :repo
            """
        ).bindparams(repo=TEMPLATE_REPO)
    )
