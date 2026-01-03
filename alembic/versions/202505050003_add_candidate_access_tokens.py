"""add candidate access token fields

Revision ID: 202505050003
Revises: 202505050002
Create Date: 2025-05-05 01:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202505050003"
down_revision: Union[str, None] = "202505050002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("candidate_sessions")}

    if "candidate_access_token_hash" not in columns:
        op.add_column(
            "candidate_sessions",
            sa.Column(
                "candidate_access_token_hash", sa.String(length=128), nullable=True
            ),
        )

    if "candidate_access_token_expires_at" not in columns:
        op.add_column(
            "candidate_sessions",
            sa.Column(
                "candidate_access_token_expires_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    if "candidate_access_token_issued_at" not in columns:
        op.add_column(
            "candidate_sessions",
            sa.Column(
                "candidate_access_token_issued_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("candidate_sessions")}
    if "ix_candidate_sessions_candidate_access_token_hash" not in indexes:
        op.create_index(
            "ix_candidate_sessions_candidate_access_token_hash",
            "candidate_sessions",
            ["candidate_access_token_hash"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index(
        "ix_candidate_sessions_candidate_access_token_hash",
        table_name="candidate_sessions",
    )
    op.drop_column("candidate_sessions", "candidate_access_token_issued_at")
    op.drop_column("candidate_sessions", "candidate_access_token_expires_at")
    op.drop_column("candidate_sessions", "candidate_access_token_hash")
