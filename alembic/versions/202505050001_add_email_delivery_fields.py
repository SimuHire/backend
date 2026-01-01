"""add email delivery + verification fields

Revision ID: 202505050001
Revises: 202504250001_add_candidate_auth0_identity
Create Date: 2025-05-05 00:01:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202505050001"
down_revision: Union[str, None] = "202504250001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidate_sessions",
        sa.Column("invite_email_status", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("invite_email_error", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("invite_email_last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("invite_email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("verification_code", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("verification_code_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "candidate_sessions",
        sa.Column("verification_code_expires_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("verification_email_last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidate_sessions", "verification_email_last_attempt_at")
    op.drop_column("candidate_sessions", "verification_email_error")
    op.drop_column("candidate_sessions", "verification_email_status")
    op.drop_column("candidate_sessions", "verification_code_expires_at")
    op.drop_column("candidate_sessions", "verification_code_sent_at")
    op.drop_column("candidate_sessions", "verification_code")
    op.drop_column("candidate_sessions", "invite_email_sent_at")
    op.drop_column("candidate_sessions", "invite_email_last_attempt_at")
    op.drop_column("candidate_sessions", "invite_email_error")
    op.drop_column("candidate_sessions", "invite_email_status")
