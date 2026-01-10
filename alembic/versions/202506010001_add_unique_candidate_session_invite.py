"""Enforce unique candidate sessions per simulation + invite email.

Revision ID: 202506010001
Revises: 202504010002, 202505150002, 202505200001
Create Date: 2025-06-01 00:00:01.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202506010001"
down_revision: Union[str, Sequence[str], None] = (
    "202504010002",
    "202505150002",
    "202505200001",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UNIQUE_NAME = "uq_candidate_sessions_simulation_invite_email"


def _dedupe_candidate_sessions(conn) -> None:
    rows = conn.execute(
        sa.text(
            """
            SELECT cs.id AS id, d.keep_id AS keep_id
            FROM candidate_sessions AS cs
            JOIN (
                SELECT
                    simulation_id,
                    LOWER(invite_email) AS invite_email,
                    MAX(id) AS keep_id,
                    COUNT(*) AS cnt
                FROM candidate_sessions
                GROUP BY simulation_id, LOWER(invite_email)
                HAVING COUNT(*) > 1
            ) AS d
                ON cs.simulation_id = d.simulation_id
               AND LOWER(cs.invite_email) = d.invite_email
            WHERE cs.id <> d.keep_id
            """
        )
    ).fetchall()

    for row in rows:
        old_id = row.id
        keep_id = row.keep_id
        conn.execute(
            sa.text(
                """
                UPDATE submissions
                SET candidate_session_id = :keep_id
                WHERE candidate_session_id = :old_id
                """
            ),
            {"keep_id": keep_id, "old_id": old_id},
        )
        conn.execute(
            sa.text(
                """
                UPDATE workspaces
                SET candidate_session_id = :keep_id
                WHERE candidate_session_id = :old_id
                """
            ),
            {"keep_id": keep_id, "old_id": old_id},
        )
        conn.execute(
            sa.text(
                """
                UPDATE fit_profiles
                SET candidate_session_id = :keep_id
                WHERE candidate_session_id = :old_id
                """
            ),
            {"keep_id": keep_id, "old_id": old_id},
        )
        conn.execute(
            sa.text("DELETE FROM candidate_sessions WHERE id = :old_id"),
            {"old_id": old_id},
        )


def upgrade() -> None:
    conn = op.get_bind()
    _dedupe_candidate_sessions(conn)
    op.create_unique_constraint(
        _UNIQUE_NAME,
        "candidate_sessions",
        ["simulation_id", "invite_email"],
    )


def downgrade() -> None:
    op.drop_constraint(_UNIQUE_NAME, "candidate_sessions", type_="unique")
