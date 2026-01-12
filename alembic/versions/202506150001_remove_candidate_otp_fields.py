"""Remove candidate OTP fields and legacy access tokens.

Revision ID: 202506150001
Revises: 202506010001
Create Date: 2025-06-15 00:00:01.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202506150001"
down_revision: Union[str, Sequence[str], None] = "202506010001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("candidate_sessions")}
    indexes = {idx["name"] for idx in inspector.get_indexes("candidate_sessions")}

    if "ix_candidate_sessions_access_token" in indexes:
        op.drop_index(
            "ix_candidate_sessions_access_token", table_name="candidate_sessions"
        )
    if "ix_candidate_sessions_candidate_access_token_hash" in indexes:
        op.drop_index(
            "ix_candidate_sessions_candidate_access_token_hash",
            table_name="candidate_sessions",
        )

    for col in (
        "access_token",
        "access_token_expires_at",
        "invite_email_verified_at",
        "candidate_access_token_hash",
        "candidate_access_token_expires_at",
        "candidate_access_token_issued_at",
        "verification_code",
        "verification_code_attempts",
        "verification_code_send_count",
        "verification_code_sent_at",
        "verification_code_expires_at",
        "verification_email_status",
        "verification_email_error",
        "verification_email_last_attempt_at",
    ):
        if col in columns:
            op.drop_column("candidate_sessions", col)


def downgrade() -> None:
    op.add_column(
        "candidate_sessions",
        sa.Column("access_token", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("invite_email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("candidate_access_token_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column(
            "candidate_access_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column(
            "candidate_access_token_issued_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("verification_code", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column(
            "verification_code_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column(
            "verification_code_send_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("verification_code_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column(
            "verification_code_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("verification_email_status", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("verification_email_error", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column(
            "verification_email_last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_candidate_sessions_access_token",
        "candidate_sessions",
        ["access_token"],
        unique=True,
    )
    op.create_index(
        "ix_candidate_sessions_candidate_access_token_hash",
        "candidate_sessions",
        ["candidate_access_token_hash"],
        unique=False,
    )
