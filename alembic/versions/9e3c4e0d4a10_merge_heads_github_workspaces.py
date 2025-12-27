"""Merge heads 81ad6f2bd717 and c4f2c76e5c3a.

This merge resolves the dual-head state created by the placeholder migration
for 81ad6f2bd717 and the GitHub workspaces migration.
"""
from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision: str = "9e3c4e0d4a10"
down_revision: Union[str, Sequence[str], None] = ("81ad6f2bd717", "c4f2c76e5c3a")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
