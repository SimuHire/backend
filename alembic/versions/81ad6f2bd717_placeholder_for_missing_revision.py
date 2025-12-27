"""Placeholder to satisfy missing revision 81ad6f2bd717.

This migration is intentionally empty and simply bridges the revision chain so
environments stamped to 81ad6f2bd717 can upgrade to the latest head.
"""
from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "81ad6f2bd717"
down_revision: Union[str, Sequence[str], None] = "3d7f8c5b6b8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op placeholder."""
    pass


def downgrade() -> None:
    """No-op placeholder."""
    pass
