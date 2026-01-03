"""Rename execution profiles to fit profiles

Revision ID: 202504010001
Revises: 202503200001
Create Date: 2025-04-01 00:00:01.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202504010001"
down_revision: Union[str, Sequence[str], None] = "202503200001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    old_table = "_".join(["execution", "profiles"])
    new_table = "fit_profiles"

    if old_table in inspector.get_table_names():
        indexes = {idx["name"] for idx in inspector.get_indexes(old_table)}
        uniques = {uc["name"] for uc in inspector.get_unique_constraints(old_table)}
        pk = inspector.get_pk_constraint(old_table).get("name")
        op.rename_table(old_table, new_table)

        if f"ix_{old_table}_candidate_session_id" in indexes:
            op.execute(
                f"ALTER INDEX ix_{old_table}_candidate_session_id "
                f"RENAME TO ix_{new_table}_candidate_session_id"
            )

        if f"uq_{old_table}_candidate_session_id" in uniques:
            op.execute(
                f"ALTER TABLE {new_table} "
                f"RENAME CONSTRAINT uq_{old_table}_candidate_session_id "
                f"TO uq_{new_table}_candidate_session_id"
            )

        if pk == f"{old_table}_pkey":
            op.execute(
                f"ALTER TABLE {new_table} "
                f"RENAME CONSTRAINT {old_table}_pkey TO {new_table}_pkey"
            )

        if bind.dialect.name == "postgresql":  # pragma: no cover - db specific
            op.execute(
                f"ALTER SEQUENCE {old_table}_id_seq "
                "RENAME TO fit_profiles_id_seq"
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    new_table = "fit_profiles"
    old_table = "_".join(["execution", "profiles"])
    if new_table in inspector.get_table_names():
        if bind.dialect.name == "postgresql":  # pragma: no cover - db specific
            op.execute(
                f"ALTER SEQUENCE fit_profiles_id_seq "
                f"RENAME TO {old_table}_id_seq"
            )

        uniques = {uc["name"] for uc in inspector.get_unique_constraints(new_table)}
        if f"uq_{new_table}_candidate_session_id" in uniques:
            op.execute(
                f"ALTER TABLE {new_table} "
                f"RENAME CONSTRAINT uq_{new_table}_candidate_session_id "
                f"TO uq_{old_table}_candidate_session_id"
            )

        pk = inspector.get_pk_constraint(new_table).get("name")
        if pk == f"{new_table}_pkey":
            op.execute(
                f"ALTER TABLE {new_table} "
                f"RENAME CONSTRAINT {new_table}_pkey TO {old_table}_pkey"
            )

        indexes = {idx["name"] for idx in inspector.get_indexes(new_table)}
        if f"ix_{new_table}_candidate_session_id" in indexes:
            op.execute(
                f"ALTER INDEX ix_{new_table}_candidate_session_id "
                f"RENAME TO ix_{old_table}_candidate_session_id"
            )

        op.rename_table(new_table, old_table)
